"""Dados de entrada da parede e suas validações.

Convenção de eixos no plano da seção transversal: X horizontal, Y vertical,
altura da parede ao longo de Z. A largura bx é medida em X e a profundidade by
em Y. Mx é o momento em torno de X (positivo comprime a face inferior) e My o
momento em torno de Y (positivo comprime a face direita). Normal de compressão
é positiva.

Unidades de entrada: bx, by e le em cm; hw em m; cobrimento em mm; fck e fyk
em MPa; forças em kN; momentos em kN·m.
"""

from dataclasses import dataclass, field

from .textos import Mensagem, Texto

ACOS = {"CA-25": 250.0, "CA-50": 500.0, "CA-60": 600.0}


@dataclass(frozen=True)
class Esforcos:
    """Conjunto de esforços na seção (kN e kN·m)."""

    N: float = 0.0
    Mx: float = 0.0
    My: float = 0.0
    Vx: float = 0.0
    Vy: float = 0.0

    def __add__(self, outro: "Esforcos") -> "Esforcos":
        return Esforcos(
            self.N + outro.N,
            self.Mx + outro.Mx,
            self.My + outro.My,
            self.Vx + outro.Vx,
            self.Vy + outro.Vy,
        )

    def __mul__(self, fator: float) -> "Esforcos":
        return Esforcos(
            self.N * fator,
            self.Mx * fator,
            self.My * fator,
            self.Vx * fator,
            self.Vy * fator,
        )

    __rmul__ = __mul__

    def nulo(self) -> bool:
        return not any((self.N, self.Mx, self.My, self.Vx, self.Vy))


@dataclass(frozen=True)
class Geometria:
    bx: float  # cm, direção X
    by: float  # cm, direção Y
    hw: float  # m, altura livre
    k: float = 1.0  # coeficiente de comprimento efetivo
    cobrimento: float = 30.0  # mm

    @property
    def lw(self) -> float:
        """Comprimento da parede (cm): a maior dimensão da seção."""
        return max(self.bx, self.by)

    @property
    def h(self) -> float:
        """Espessura da parede (cm): a menor dimensão da seção."""
        return min(self.bx, self.by)

    @property
    def eixo_comprimento(self) -> str:
        """Eixo ao longo do qual a parede se estende ("X" ou "Y")."""
        return "X" if self.bx >= self.by else "Y"


@dataclass(frozen=True)
class Materiais:
    fck: float = 30.0  # MPa
    aco: str = "CA-50"

    @property
    def fyk(self) -> float:
        return ACOS[self.aco]


@dataclass(frozen=True)
class Acoes:
    """Esforços característicos separados por tipo de ação."""

    G: Esforcos = field(default_factory=Esforcos)  # permanente (D no ACI)
    Q: Esforcos = field(default_factory=Esforcos)  # variável (L no ACI)
    W: Esforcos = field(default_factory=Esforcos)  # vento, testado com + e −


@dataclass(frozen=True)
class Opcoes:
    psi0: float = 0.5  # fator de combinação de Q (NBR), residencial
    aci_reducao_L: bool = True  # ACI 5.3.3: 0,5·L nas combinações c e d
    le: float | None = None  # cm; None usa máx(0,10·lw; 2h)
    phi_extremidade: float = 16.0  # mm
    phi_alma: float = 10.0  # mm


@dataclass(frozen=True)
class Parede:
    geometria: Geometria
    materiais: Materiais
    acoes: Acoes
    opcoes: Opcoes = field(default_factory=Opcoes)

    @property
    def le(self) -> float:
        """Comprimento de cada zona de extremidade (cm)."""
        if self.opcoes.le is not None:
            return self.opcoes.le
        g = self.geometria
        return max(0.10 * g.lw, 2.0 * g.h)


def _erro(campo: str, pt: str, en: str) -> Mensagem:
    return Mensagem("erro", campo, Texto(pt, en))


def _aviso(campo: str, pt: str, en: str) -> Mensagem:
    return Mensagem("aviso", campo, Texto(pt, en))


def validar(parede: Parede) -> list[Mensagem]:
    """Confere a entrada e devolve a lista de erros e avisos.

    Qualquer mensagem de nível "erro" impede o cálculo.
    """
    msgs: list[Mensagem] = []
    g, m, op = parede.geometria, parede.materiais, parede.opcoes

    for campo, valor in (("bx", g.bx), ("by", g.by), ("hw", g.hw), ("k", g.k)):
        if valor <= 0:
            msgs.append(
                _erro(
                    campo,
                    f"{campo} deve ser maior que zero.",
                    f"{campo} must be greater than zero.",
                )
            )
    if g.cobrimento <= 0:
        msgs.append(
            _erro(
                "cobrimento",
                "O cobrimento deve ser maior que zero.",
                "Concrete cover must be greater than zero.",
            )
        )
    if any(msg.nivel == "erro" for msg in msgs):
        return msgs

    if g.h < 14:
        msgs.append(
            _erro(
                "h",
                f"Espessura h = {g.h:.1f} cm é menor que o mínimo de 14 cm (NBR 6118, 13.2.3).",
                f"Thickness h = {g.h:.1f} cm is below the 14 cm minimum (NBR 6118, 13.2.3).",
            )
        )
    elif g.h < 19:
        gn = gama_n(g.h)
        msgs.append(
            _aviso(
                "h",
                f"Espessura h = {g.h:.1f} cm < 19 cm: os esforços da NBR são multiplicados por γn = {gn:.2f} (13.2.3).",
                f"Thickness h = {g.h:.1f} cm < 19 cm: NBR design forces are multiplied by γn = {gn:.2f} (13.2.3).",
            )
        )

    if not 20 <= m.fck <= 90:
        msgs.append(
            _erro(
                "fck",
                f"fck = {m.fck:g} MPa fora da faixa da NBR 6118 (20 a 90 MPa).",
                f"fck = {m.fck:g} MPa is outside the NBR 6118 range (20 to 90 MPa).",
            )
        )
    if m.aco not in ACOS:
        msgs.append(
            _erro(
                "aco",
                f"Aço {m.aco} não reconhecido; use CA-25, CA-50 ou CA-60.",
                f"Steel {m.aco} not recognized; use CA-25, CA-50 or CA-60.",
            )
        )

    if parede.acoes.G.nulo() and parede.acoes.Q.nulo() and parede.acoes.W.nulo():
        msgs.append(
            _erro(
                "acoes",
                "Informe ao menos um esforço característico.",
                "Enter at least one characteristic load effect.",
            )
        )

    if not 0 <= op.psi0 <= 1:
        msgs.append(
            _erro(
                "psi0",
                "ψ0 deve estar entre 0 e 1.",
                "ψ0 must be between 0 and 1.",
            )
        )

    le = parede.le
    if le <= 0:
        msgs.append(
            _erro(
                "le",
                "O comprimento da zona de extremidade deve ser maior que zero.",
                "Boundary zone length must be greater than zero.",
            )
        )
    elif le > g.lw / 3:
        msgs.append(
            _aviso(
                "le",
                f"Zona de extremidade le = {le:.1f} cm maior que lw/3 = {g.lw / 3:.1f} cm.",
                f"Boundary zone le = {le:.1f} cm exceeds lw/3 = {g.lw / 3:.1f} cm.",
            )
        )

    return msgs


def gama_n(h_cm: float) -> float:
    """Coeficiente adicional γn da NBR 6118 (13.2.3) para h < 19 cm."""
    return 1.95 - 0.05 * h_cm if h_cm < 19 else 1.0
