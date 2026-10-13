"""Escolha da metodologia de cálculo a partir da geometria e dos esforços.

Cada decisão guarda o critério que a disparou, em português e inglês, para
aparecer no memorial.
"""

from dataclasses import dataclass

from .combinacoes import Combinacao
from .entrada import Esforcos, Parede
from .textos import Texto

LAMBDA_MAX_V1 = 90.0  # acima disso a versão 1 não dimensiona (método geral)


@dataclass(frozen=True)
class Decisao:
    chave: str  # "tipo", "regime", "esbeltez_nbr", "esbeltez_aci"
    resultado: str  # código estável, ex. "pilar-parede", "B", "dispensada"
    texto: Texto  # classificação + critério legível


@dataclass(frozen=True)
class Mapeamento:
    """Quais esforços atuam no plano da parede e quais fora dele."""

    eixo_comprimento: str
    M_no_plano: str  # "Mx" ou "My"
    M_fora_plano: str
    V_no_plano: str  # "Vx" ou "Vy"
    V_fora_plano: str

    def separar(self, e: Esforcos) -> dict[str, float]:
        return {
            "N": e.N,
            "M_no_plano": getattr(e, self.M_no_plano),
            "M_fora_plano": getattr(e, self.M_fora_plano),
            "V_no_plano": getattr(e, self.V_no_plano),
            "V_fora_plano": getattr(e, self.V_fora_plano),
        }


def mapeamento(parede: Parede) -> Mapeamento:
    """Parede ao longo de X: My e Vx no plano. Ao longo de Y: Mx e Vy no plano."""
    if parede.geometria.eixo_comprimento == "X":
        return Mapeamento("X", "My", "Mx", "Vx", "Vy")
    return Mapeamento("Y", "Mx", "My", "Vy", "Vx")


def _n(v: float) -> str:
    return f"{v:.2f}".replace(".", ",")


def tipo_elemento(parede: Parede) -> Decisao:
    g = parede.geometria
    r = g.lw / g.h
    if r >= 5:
        return Decisao(
            "tipo",
            "pilar-parede",
            Texto(
                f"Pilar-parede: lw/h = {_n(r)} ≥ 5 (NBR 6118, 14.4.2.4); parede pelo ACI 318, Cap. 11.",
                f"Wall: lw/h = {_n(r)} ≥ 5 (NBR 6118, 14.4.2.4); ACI 318 Chapter 11 wall.",
            ),
        )
    return Decisao(
        "tipo",
        "pilar",
        Texto(
            f"Pilar: lw/h = {_n(r)} < 5; dimensionado como pilar (NBR) e coluna (ACI 318, Cap. 10).",
            f"Column: lw/h = {_n(r)} < 5; designed as a column (NBR, ACI 318 Chapter 10).",
        ),
    )


def regime(parede: Parede) -> Decisao:
    g = parede.geometria
    r = g.hw * 100 / g.lw
    if r >= 2:
        return Decisao(
            "regime",
            "B",
            Texto(
                f"Parede esbelta, região B: hw/lw = {_n(r)} ≥ 2. Flexão por seção plana e cortante pela treliça de Mörsch.",
                f"Slender wall, B-region: hw/lw = {_n(r)} ≥ 2. Plane-section flexure and Mörsch truss shear.",
            ),
        )
    return Decisao(
        "regime",
        "D",
        Texto(
            f"Parede baixa, região D: hw/lw = {_n(r)} < 2. Modelo de bielas e tirantes (NBR Seção 22; ACI Cap. 23).",
            f"Squat wall, D-region: hw/lw = {_n(r)} < 2. Strut-and-tie model (NBR Section 22; ACI Chapter 23).",
        ),
    )


def lambda_fora_plano(parede: Parede) -> float:
    """Índice de esbeltez fora do plano: λ = 3,46·k·hw/h."""
    g = parede.geometria
    return 3.46 * g.k * g.hw * 100 / g.h


def lambda1_nbr(parede: Parede, comb: Combinacao, alfa_b: float = 1.0) -> float:
    """λ1 = (25 + 12,5·e1/h)/αb, limitado a 35 ≤ λ1 ≤ 90 (NBR 6118, 15.8.2).

    e1 é a excentricidade de 1ª ordem fora do plano. αb = 1,0 por padrão
    (sem informação sobre os momentos nas extremidades).
    """
    sep = mapeamento(parede).separar(comb.esforcos)
    h_m = parede.geometria.h / 100
    e1 = abs(sep["M_fora_plano"] / sep["N"]) if sep["N"] > 0 else 0.0
    lam1 = (25 + 12.5 * e1 / h_m) / alfa_b
    return min(max(lam1, 35.0), 90.0)


def esbeltez_nbr(parede: Parede, comb: Combinacao) -> Decisao:
    lam = lambda_fora_plano(parede)
    lam1 = lambda1_nbr(parede, comb)
    if lam <= lam1:
        return Decisao(
            "esbeltez_nbr",
            "dispensada",
            Texto(
                f"λ = {_n(lam)} ≤ λ1 = {_n(lam1)}: efeitos locais de 2ª ordem dispensados (15.8.2).",
                f"λ = {_n(lam)} ≤ λ1 = {_n(lam1)}: local second-order effects neglected (15.8.2).",
            ),
        )
    if lam <= LAMBDA_MAX_V1:
        return Decisao(
            "esbeltez_nbr",
            "pilar-padrao",
            Texto(
                f"λ1 = {_n(lam1)} < λ = {_n(lam)} ≤ 90: pilar-padrão com curvatura aproximada (15.8.3.3.2), em faixas (15.9).",
                f"λ1 = {_n(lam1)} < λ = {_n(lam)} ≤ 90: model column with approximate curvature (15.8.3.3.2), by strips (15.9).",
            ),
        )
    return Decisao(
        "esbeltez_nbr",
        "fora-do-escopo",
        Texto(
            f"λ = {_n(lam)} > 90: exige método geral com fluência, fora do escopo da versão 1.",
            f"λ = {_n(lam)} > 90: requires the general method with creep, outside version 1 scope.",
        ),
    )


def esbeltez_aci(parede: Parede) -> Decisao:
    """k·lu/r com r = 0,3·h; limite de 22 (ACI 318, 6.2.5)."""
    g = parede.geometria
    klr = g.k * g.hw * 100 / (0.3 * g.h)
    if klr <= 22:
        return Decisao(
            "esbeltez_aci",
            "dispensada",
            Texto(
                f"k·lu/r = {_n(klr)} ≤ 22: esbeltez dispensada (6.2.5).",
                f"k·lu/r = {_n(klr)} ≤ 22: slenderness neglected (6.2.5).",
            ),
        )
    if klr <= 100:
        return Decisao(
            "esbeltez_aci",
            "amplificacao",
            Texto(
                f"k·lu/r = {_n(klr)} > 22: amplificação de momentos (6.6.4).",
                f"k·lu/r = {_n(klr)} > 22: moment magnification (6.6.4).",
            ),
        )
    return Decisao(
        "esbeltez_aci",
        "fora-do-escopo",
        Texto(
            f"k·lu/r = {_n(klr)} > 100: exige análise de 2ª ordem (6.2.6), fora do escopo da versão 1.",
            f"k·lu/r = {_n(klr)} > 100: requires second-order analysis (6.2.6), outside version 1 scope.",
        ),
    )


def solicitacao(comb: Combinacao) -> Texto:
    """Tipo de solicitação de uma combinação (compressão positiva)."""
    e = comb.esforcos
    tem_mx, tem_my = abs(e.Mx) > 1e-9, abs(e.My) > 1e-9
    if not (tem_mx or tem_my):
        if e.N > 0:
            return Texto("Compressão centrada", "Concentric compression")
        if e.N < 0:
            return Texto("Tração centrada", "Concentric tension")
        return Texto("Sem esforço normal nem momento", "No axial force or moment")
    obliqua = tem_mx and tem_my
    if e.N > 0:
        return (
            Texto("Flexo-compressão oblíqua", "Biaxial bending with compression")
            if obliqua
            else Texto("Flexo-compressão normal", "Uniaxial bending with compression")
        )
    if e.N < 0:
        return (
            Texto("Flexo-tração oblíqua", "Biaxial bending with tension")
            if obliqua
            else Texto("Flexo-tração normal", "Uniaxial bending with tension")
        )
    return (
        Texto("Flexão oblíqua", "Biaxial bending")
        if obliqua
        else Texto("Flexão simples", "Uniaxial bending")
    )
