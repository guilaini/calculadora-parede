"""Arranjo das barras da parede: zonas de extremidade concentradas e alma distribuída."""

import math

from .secao_fibras import Barra

ESPACAMENTO_EXTREMIDADE = 0.10  # m, entre barras de uma face na zona de extremidade
ESPACAMENTO_ALMA = 0.20  # m, entre barras de uma face na alma


def barras_parede(
    bx: float,
    by: float,
    cobrimento: float,
    le: float,
    As_extremidade: float,
    As_alma_por_m: float,
    phi_extremidade: float = 0.016,
    phi_alma: float = 0.010,
    phi_estribo: float = 0.0063,
) -> list[Barra]:
    """Barras equivalentes da seção (unidades em m e m²).

    As_extremidade é a área total de UMA zona de extremidade (as duas faces);
    As_alma_por_m é a área por metro de UMA face da alma. As barras são
    equivalentes em área: a escolha de diâmetros comerciais vem depois.
    """
    ao_longo_de_x = bx >= by
    lw, h = (bx, by) if ao_longo_de_x else (by, bx)

    t_face = h / 2 - cobrimento - phi_estribo - phi_extremidade / 2
    s_borda = lw / 2 - cobrimento - phi_estribo - phi_extremidade / 2
    s_fim_zona = lw / 2 - le

    locais: list[tuple[float, float, float]] = []  # (s, t, área)

    if As_extremidade > 0:
        comprimento = max(s_borda - s_fim_zona, 0.0)
        n = max(2, int(math.floor(comprimento / ESPACAMENTO_EXTREMIDADE + 1e-9)) + 1)
        area = As_extremidade / (2 * n)
        for lado in (1, -1):
            for i in range(n):
                s = lado * (s_borda - i * comprimento / (n - 1))
                for t in (t_face, -t_face):
                    locais.append((s, t, area))

    comprimento_alma = 2 * s_fim_zona
    if As_alma_por_m > 0 and comprimento_alma > 0:
        t_alma = h / 2 - cobrimento - phi_estribo - phi_alma / 2
        n = max(1, int(math.ceil(comprimento_alma / ESPACAMENTO_ALMA)) - 1)
        area = As_alma_por_m * comprimento_alma / n
        for i in range(n):
            s = -s_fim_zona + (i + 1) * comprimento_alma / (n + 1)
            for t in (t_alma, -t_alma):
                locais.append((s, t, area))

    if ao_longo_de_x:
        return [Barra(s, t, a) for s, t, a in locais]
    return [Barra(t, s, a) for s, t, a in locais]


BITOLAS = (5.0, 6.3, 8.0, 10.0, 12.5, 16.0, 20.0, 25.0, 32.0)  # mm, NBR 7480


def area_barra(phi_mm: float) -> float:
    """Área de uma barra em cm²."""
    return math.pi * (phi_mm / 10) ** 2 / 4


def barras_zona(As_cm2: float, phi_mm: float, minimo: int = 4) -> tuple[int, float]:
    """Número par de barras φ para cobrir As (cm²) em uma zona de extremidade."""
    n = max(minimo, math.ceil(As_cm2 / area_barra(phi_mm) - 1e-9))
    n += n % 2
    return n, n * area_barra(phi_mm)


def espacamento(As_cm2_m: float, phi_mm: float, s_max_cm: float) -> tuple[float, float]:
    """Espaçamento (cm, múltiplo de 2,5) de barras φ para cobrir As por metro."""
    s = s_max_cm if As_cm2_m <= 0 else min(s_max_cm, 100 * area_barra(phi_mm) / As_cm2_m)
    s = max(5.0, math.floor(s / 2.5 + 1e-9) * 2.5)
    return s, 100 * area_barra(phi_mm) / s


def bitola_estribo(phi_long_mm: float) -> float:
    """Menor bitola comercial com φt ≥ 5 mm e φt ≥ φ/4 (NBR 6118, 18.4.3)."""
    return next(b for b in BITOLAS if b >= max(5.0, phi_long_mm / 4))
