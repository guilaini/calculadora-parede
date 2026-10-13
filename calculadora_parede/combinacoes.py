"""Combinações últimas de cálculo de cada norma, a partir das ações características.

Cada ação variável é testada presente e ausente (variável favorável entra como
zero), e o vento é testado nos dois sentidos.
"""

from dataclasses import dataclass

from .entrada import Acoes, Esforcos, Parede, gama_n


@dataclass(frozen=True)
class Combinacao:
    norma: str  # "NBR" ou "ACI"
    nome: str  # rótulo curto, ex. "5.3.1d" ou "Q principal"
    expressao: str  # ex. "1,2·D + 1,0·W + 0,5·L"
    fG: float
    fQ: float
    fW: float  # com sinal: negativo = vento no sentido oposto
    esforcos: Esforcos


def _fmt(f: float) -> str:
    """Fator com ao menos uma casa decimal: 1,0 · 0,5 · 0,84."""
    txt = f"{abs(f):.2f}".rstrip("0")
    if txt.endswith("."):
        txt += "0"
    return txt.replace(".", ",")


def _expressao(fG: float, fQ: float, fW: float, nomes: tuple[str, str, str]) -> str:
    partes = [f"{_fmt(fG)}·{nomes[0]}"]
    if fQ:
        partes.append(f"+ {_fmt(fQ)}·{nomes[1]}")
    if fW:
        sinal = "+" if fW > 0 else "−"
        partes.append(f"{sinal} {_fmt(fW)}·{nomes[2]}")
    return " ".join(partes)


def _montar(
    norma: str,
    nome: str,
    fG: float,
    fQ: float,
    fW: float,
    acoes: Acoes,
    multiplicador: float = 1.0,
) -> Combinacao:
    nomes = ("G", "Q", "W") if norma == "NBR" else ("D", "L", "W")
    esf = (acoes.G * fG + acoes.Q * fQ + acoes.W * fW) * multiplicador
    expr = _expressao(fG, fQ, fW, nomes)
    if multiplicador != 1.0:
        expr = f"{_fmt(multiplicador)}·({expr})"
    return Combinacao(norma, nome, expr, fG, fQ, fW, esf)


def _sinais_vento(acoes: Acoes) -> tuple[float, ...]:
    return (1.0, -1.0) if not acoes.W.nulo() else ()


def _sem_repetidas(combs: list[Combinacao]) -> list[Combinacao]:
    vistas, saida = set(), []
    for c in combs:
        chave = (c.fG, c.fQ, c.fW)
        if chave not in vistas:
            vistas.add(chave)
            saida.append(c)
    return saida


def combinacoes_nbr(parede: Parede) -> list[Combinacao]:
    """Combinações últimas normais da NBR 6118 (11.7, Tabela 11.1).

    γg = 1,4 (desfavorável) ou 1,0 (favorável); γq = 1,4; ψ0 do vento = 0,6.
    Para h < 19 cm, todos os esforços são multiplicados por γn (13.2.3).
    """
    a, psi0 = parede.acoes, parede.opcoes.psi0
    gn = gama_n(parede.geometria.h)
    tem_Q = not a.Q.nulo()
    combs: list[Combinacao] = []
    for fG in (1.4, 1.0):
        rotulo_g = "" if fG == 1.4 else ", G favorável"
        combs.append(_montar("NBR", f"Só permanente{rotulo_g}", fG, 0, 0, a, gn))
        if tem_Q:
            combs.append(_montar("NBR", f"Q principal{rotulo_g}", fG, 1.4, 0, a, gn))
        for s in _sinais_vento(a):
            if tem_Q:
                combs.append(
                    _montar("NBR", f"Q principal{rotulo_g}", fG, 1.4, s * 1.4 * 0.6, a, gn)
                )
                combs.append(
                    _montar("NBR", f"W principal{rotulo_g}", fG, 1.4 * psi0, s * 1.4, a, gn)
                )
            combs.append(_montar("NBR", f"W principal{rotulo_g}", fG, 0, s * 1.4, a, gn))
    return _sem_repetidas(combs)


def combinacoes_aci(parede: Parede) -> list[Combinacao]:
    """Combinações de resistência do ACI 318-25 (5.3.1).

    Com a redução de 5.3.3 ligada, L entra com 0,5 nas combinações c e d.
    """
    a = parede.acoes
    fL = 0.5 if parede.opcoes.aci_reducao_L else 1.0
    tem_L = not a.Q.nulo()
    combs: list[Combinacao] = [_montar("ACI", "5.3.1a", 1.4, 0, 0, a)]
    if tem_L:
        combs.append(_montar("ACI", "5.3.1b", 1.2, 1.6, 0, a))
        combs.append(_montar("ACI", "5.3.1c", 1.2, fL, 0, a))
    combs.append(_montar("ACI", "5.3.1b", 1.2, 0, 0, a))
    for s in _sinais_vento(a):
        combs.append(_montar("ACI", "5.3.1c", 1.2, 0, s * 0.5, a))
        if tem_L:
            combs.append(_montar("ACI", "5.3.1d", 1.2, fL, s * 1.0, a))
        combs.append(_montar("ACI", "5.3.1d", 1.2, 0, s * 1.0, a))
        combs.append(_montar("ACI", "5.3.1f", 0.9, 0, s * 1.0, a))
    return _sem_repetidas(combs)
