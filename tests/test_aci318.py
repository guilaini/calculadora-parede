"""Dimensionamento completo pelo ACI 318-25."""

import math

import pytest

from calculadora_parede.aci318 import _alpha_c, dimensionar_aci
from calculadora_parede.entrada import Acoes, Esforcos, Geometria, Materiais, Opcoes, Parede


def parede(G, Q=None, W=None, bx=300, by=20, hw=3.0, fck=30, **op):
    return Parede(Geometria(bx, by, hw), Materiais(fck), Acoes(G=G, Q=Q or Esforcos(), W=W or Esforcos()), Opcoes(**op))


@pytest.fixture(scope="module")
def exemplo():
    return dimensionar_aci(parede(
        Esforcos(N=800, Mx=4, My=150, Vx=10), Esforcos(N=300, Mx=2, My=60), Esforcos(My=1800, Vx=300),
    ))


def test_alpha_c():
    assert _alpha_c(1.0) == 0.25
    assert _alpha_c(1.75) == pytest.approx(0.21)
    assert _alpha_c(3.0) == 0.17


def test_exemplo_governado_por_09D_mais_W(exemplo):
    assert exemplo.util_flexao == pytest.approx(1.0, abs=0.01)
    assert exemplo.comb_flexao.startswith("5.3.1f")
    assert 2.0 < exemplo.As_extremidade < 3.5


def test_amplificacao_de_momentos(exemplo):
    # k·lu/r = 50 > 22: momentos fora do plano amplificados
    assert any(c.delta > 1.0 for c in exemplo.combinacoes)
    passo = next(p for p in exemplo.memorial.passos if p.titulo.pt.startswith("Amplificação"))
    assert "delta" in passo.simbolica


def test_cortante_alto_exige_taxa_calculada():
    # parede esbelta (hw/lw = 3): αc = 0,17
    p = parede(Esforcos(N=1000, Vx=1500), hw=9.0, by=25)
    r = dimensionar_aci(p)
    Acv = 0.25 * 3.0
    Vu = 1.4 * 1500
    rho_t = (Vu / 0.75 - 0.17 * math.sqrt(30) * Acv * 1e3) / (500e3 * Acv)
    assert r.As_horizontal_face == pytest.approx(rho_t * 0.25 / 2 * 1e4, rel=1e-3)


def test_compressao_baixa_usa_minimo():
    r = dimensionar_aci(parede(Esforcos(N=300)))
    assert r.governa.pt == "Armadura mínima"
    assert r.As_alma_face == pytest.approx(0.0012 * 20 / 2 * 100)  # ρl = 0,0012, por face


def test_reducao_de_L_altera_combinacao():
    G, Q, W = Esforcos(N=500, My=50), Esforcos(N=800, My=100), Esforcos(My=900, Vx=100)
    com = dimensionar_aci(parede(G, Q, W))
    sem = dimensionar_aci(parede(G, Q, W, aci_reducao_L=False))
    exprs_com = {c.comb.expressao for c in com.combinacoes}
    exprs_sem = {c.comb.expressao for c in sem.combinacoes}
    assert "1,2·D + 0,5·L + 1,0·W" in exprs_com and "1,2·D + 1,0·L + 1,0·W" in exprs_sem
