"""Leis constitutivas do concreto e do aço de cada norma.

Convenção: deformação e tensão de compressão são positivas. Tensões em MPa,
deformações adimensionais (0,0035 = 3,5‰).
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ConcretoNBR:
    """Diagrama parábola-retângulo da NBR 6118 (8.2.10.1)."""

    fck: float
    gama_c: float = 1.4

    @property
    def fcd(self) -> float:
        return self.fck / self.gama_c

    @property
    def eta_c(self) -> float:
        # Fator de fragilidade para fck > 40 MPa. A confirmar no texto da norma.
        return 1.0 if self.fck <= 40 else (40.0 / self.fck) ** (1.0 / 3.0)

    @property
    def sigma_cd(self) -> float:
        return 0.85 * self.eta_c * self.fcd

    @property
    def eps_c2(self) -> float:
        if self.fck <= 50:
            return 2.0e-3
        return (2.0 + 0.085 * (self.fck - 50) ** 0.53) * 1e-3

    @property
    def eps_cu(self) -> float:
        if self.fck <= 50:
            return 3.5e-3
        return (2.6 + 35.0 * ((90 - self.fck) / 100) ** 4) * 1e-3

    @property
    def n(self) -> float:
        if self.fck <= 50:
            return 2.0
        return 1.4 + 23.4 * ((90 - self.fck) / 100) ** 4

    def tensao(self, eps: np.ndarray) -> np.ndarray:
        e = np.clip(eps, 0.0, None)
        parabola = self.sigma_cd * (1.0 - (1.0 - np.minimum(e, self.eps_c2) / self.eps_c2) ** self.n)
        return np.where(eps <= 0, 0.0, parabola)


@dataclass(frozen=True)
class ConcretoACI:
    """Bloco retangular equivalente do ACI 318 (22.2.2)."""

    fc: float  # f'c em MPa
    eps_cu: float = 0.003

    @property
    def beta1(self) -> float:
        b = 0.85 - 0.05 * (self.fc - 28.0) / 7.0
        return float(min(0.85, max(0.65, b)))

    @property
    def eps_c2(self) -> float:
        # Sem ramo parabólico: a compressão uniforme pivota no próprio εcu.
        return self.eps_cu

    def tensao_bloco(self, v: np.ndarray, v_max: float, c: float) -> np.ndarray:
        """0,85·f'c nas fibras dentro da profundidade a = β1·c a partir da borda comprimida."""
        a = self.beta1 * c
        return np.where(v >= v_max - a, 0.85 * self.fc, 0.0)


@dataclass(frozen=True)
class Aco:
    """Aço elástico-perfeitamente plástico, simétrico em tração e compressão."""

    fy: float  # MPa (fyd na NBR, fy no ACI)
    Es: float  # MPa

    @property
    def eps_y(self) -> float:
        return self.fy / self.Es

    def tensao(self, eps: np.ndarray) -> np.ndarray:
        return np.clip(eps * self.Es, -self.fy, self.fy)


def aco_nbr(fyk: float, gama_s: float = 1.15) -> Aco:
    return Aco(fy=fyk / gama_s, Es=210_000.0)


def aco_aci(fy: float) -> Aco:
    return Aco(fy=fy, Es=200_000.0)
