"""Registro das equações usadas, para o memorial bilíngue."""

from dataclasses import dataclass, field

from .textos import Texto


@dataclass(frozen=True)
class Passo:
    titulo: Texto
    simbolica: str  # LaTeX da equação na forma simbólica
    valores: str  # LaTeX com os valores substituídos
    resultado: str  # ex. "V_{Rd2} = 1.234,5\\ kN"
    item: str  # item da norma, ex. "NBR 6118, 17.4.2.2"


@dataclass
class Memorial:
    passos: list[Passo] = field(default_factory=list)

    def add(self, pt: str, en: str, simbolica: str, valores: str, resultado: str, item: str) -> None:
        self.passos.append(Passo(Texto(pt, en), simbolica, valores, resultado, item))


def n(v: float, casas: int = 2) -> str:
    """Número no formato brasileiro para o LaTeX (vírgula decimal, ponto de milhar)."""
    txt = f"{v:,.{casas}f}"
    return txt.replace(",", "X").replace(".", "{,}").replace("X", ".")
