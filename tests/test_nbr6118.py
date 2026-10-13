"""Dimensionamento completo pela NBR 6118:2026."""

import math

import pytest

from calculadora_parede.entrada import Acoes, Esforcos, Geometria, Materiais, Parede
from calculadora_parede.nbr6118 import dimensionar_nbr


def parede(G, Q=None, W=None, bx=300, by=20, hw=3.0, fck=30):
    return Parede(Geometria(bx, by, hw), Materiais(fck), Acoes(G=G, Q=Q or Esforcos(), W=W or Esforcos()))


@pytest.fixture(scope="module")
def exemplo():
    return dimensionar_nbr(parede(
        Esforcos(N=800, Mx=4, My=150, Vx=10), Esforcos(N=300, Mx=2, My=60), Esforcos(My=1800, Vx=300),
    ))


def test_compressao_baixa_usa_armadura_minima():
    r = dimensionar_nbr(parede(Esforcos(N=500)))
    assert r.governa.pt == "Armadura mínima"
    # zona de 40 × 20 cm: 0,4% = 3,2 cm², e o total da seção atende 0,4%·Ac
    assert r.As_extremidade == pytest.approx(3.2, rel=1e-3)
    assert 2 * r.As_extremidade + 2 * r.As_alma_face * 2.2 >= 0.004 * 6000


def test_exemplo_flexao_governada_pelo_vento(exemplo):
    assert 6.5 < exemplo.As_extremidade < 7.5
    assert exemplo.util_flexao == pytest.approx(1.0, abs=0.01)
    assert "1,4·W" in exemplo.comb_flexao
    assert exemplo.barras_extremidade.startswith("4 φ16")


def test_cortante_no_plano_valores_de_norma(exemplo):
    passos = {p.titulo.pt: p for p in exemplo.memorial.passos}
    vrd2 = passos["Compressão diagonal do concreto (Modelo I, θ = 45°)"].resultado
    assert "2.443{,}9" in vrd2  # 0,27·0,88·21,43·0,20·2,40 MN
    vc = passos["Parcela do concreto e armadura horizontal (treliça de Mörsch)"].valores
    fctd = 0.7 * 0.3 * 30 ** (2 / 3) / 1.4
    assert f"{0.6 * fctd * 1e3 * 0.2 * 2.4:.1f}".replace(".", "{,}") in vc


def test_parede_baixa_verifica_biela(exemplo):
    titulos = [p.titulo.pt for p in exemplo.memorial.passos]
    assert "Bielas e tirantes: biela diagonal principal" in titulos


def test_segunda_ordem_entra_quando_esbelta(exemplo):
    assert any(c.segunda_ordem > 0 for c in exemplo.combinacoes)  # λ = 51,9 > λ1 = 35


def test_tracao_com_cortante_exige_armadura_horizontal():
    r = dimensionar_nbr(parede(Esforcos(N=-600, My=100, Vx=900), hw=9.0, by=25))
    # Vc = 0 em tração com a linha neutra fora da seção: estribos levam todo o cortante
    d, fywd = 0.8 * 3.0, 500 / 1.15
    esperado = 1.4 * 900 / (0.9 * d * fywd * 1e3) / 2 * 1e4
    assert r.As_horizontal_face == pytest.approx(esperado, rel=1e-3)


def test_secao_insuficiente_gera_erro():
    r = dimensionar_nbr(parede(Esforcos(N=1000, My=20000)))
    assert any(m.nivel == "erro" and m.campo == "flexao" for m in r.mensagens)
