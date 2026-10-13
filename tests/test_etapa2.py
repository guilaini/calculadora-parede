"""Seção por fibras conferida contra cálculos manuais conhecidos."""

import numpy as np
import pytest

from calculadora_parede.armadura import barras_parede
from calculadora_parede.materiais import ConcretoACI, ConcretoNBR, aco_aci, aco_nbr
from calculadora_parede.secao_fibras import Barra, Secao


def viga(norma, barras):
    """Seção 20 × 50 cm (bx × by), fck = f'c = 30 MPa, CA-50."""
    if norma == "NBR":
        return Secao(0.20, 0.50, barras, ConcretoNBR(30), aco_nbr(500), tamanho_fibra=0.004)
    return Secao(0.20, 0.50, barras, ConcretoACI(30), aco_aci(500), tamanho_fibra=0.004)


def test_compressao_pura_nbr_sem_aco():
    s = viga("NBR", [])
    assert s.N_max() == pytest.approx(0.85 * 30 / 1.4 * 0.20 * 0.50 * 1e3, rel=1e-3)


def test_tracao_pura_so_aco():
    barras = [Barra(0, 0.2, 2e-4), Barra(0, -0.2, 2e-4)]
    s = viga("NBR", barras)
    assert s.N_min() == pytest.approx(-4e-4 * 500 / 1.15 * 1e3, rel=1e-6)


def test_flexao_simples_nbr():
    """Armadura de 4 cm² no topo (d = 45 cm); Mx positivo traciona o topo.

    Bloco retangular 0,8x: x = 5,97 cm e MRd = 173,9·(0,45 − 0,4·0,0597) = 74,1 kN·m.
    """
    s = viga("NBR", [Barra(0, 0.20, 4e-4)])
    contorno = s.contorno(0.0, 72)
    mx_max = contorno[:, 0].max()
    assert mx_max == pytest.approx(74.1, rel=0.01)


def test_flexao_simples_aci():
    """a = 3,92 cm, Mn = 200·(0,45 − 0,0196) = 86,1 kN·m, εt = 0,026 → φ = 0,90 → φMn = 77,5."""
    s = viga("ACI", [Barra(0, 0.20, 4e-4)])
    mx_max = s.contorno(0.0, 72)[:, 0].max()
    assert mx_max == pytest.approx(77.5, rel=0.01)


def test_teto_de_compressao_aci():
    s = viga("ACI", [Barra(0, 0.2, 4e-4), Barra(0, -0.2, 4e-4)])
    P0 = 0.85 * 30 * (0.1 - 8e-4) + 500 * 8e-4
    assert s.N_max() == pytest.approx(0.80 * 0.65 * P0 * 1e3, rel=1e-6)


def test_sinais_dos_momentos():
    """Mx positivo comprime a face inferior; My positivo comprime a face direita."""
    s = viga("NBR", [Barra(x, y, 2e-4) for x in (-0.06, 0.06) for y in (-0.2, 0.2)])
    baixo = s.ponto(1.5 * np.pi, 1.5)  # direção mais comprimida: −Y
    direita = s.ponto(0.0, 1.5)  # direção mais comprimida: +X
    assert baixo.Mx > 0 and abs(baixo.My) < 1e-6
    assert direita.My > 0 and abs(direita.Mx) < 1e-6


def test_utilizacao_simetrica_e_monotona():
    barras = barras_parede(3.0, 0.20, 0.030, 0.40, 20e-4, 2.5e-4)
    s = Secao(3.0, 0.20, barras, ConcretoNBR(30), aco_nbr(500))
    u1 = s.utilizacao(1500, 0, 800)
    assert s.utilizacao(1500, 0, -800) == pytest.approx(u1, rel=0.02)
    assert s.utilizacao(1500, 0, 1600) > u1
    assert s.utilizacao(1500, 30, 800) > u1  # momento fora do plano também consome


def test_arranjo_das_barras():
    barras = barras_parede(3.0, 0.20, 0.030, 0.40, 20e-4, 2.5e-4)
    area_ext = sum(b.area for b in barras if b.x > 1.09)
    assert area_ext == pytest.approx(20e-4)
    area_alma = sum(b.area for b in barras if abs(b.x) < 1.09)
    assert area_alma == pytest.approx(2 * 2.5e-4 * 2.2)
    # parede ao longo de Y: mesmas barras giradas
    giradas = barras_parede(0.20, 3.0, 0.030, 0.40, 20e-4, 2.5e-4)
    assert sum(b.area for b in giradas if b.y > 1.09) == pytest.approx(20e-4)
