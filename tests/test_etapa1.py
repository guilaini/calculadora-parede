import pytest

from calculadora_parede.classificacao import (
    esbeltez_aci,
    esbeltez_nbr,
    lambda_fora_plano,
    mapeamento,
    regime,
    solicitacao,
    tipo_elemento,
)
from calculadora_parede.combinacoes import combinacoes_aci, combinacoes_nbr
from calculadora_parede.entrada import (
    Acoes,
    Esforcos,
    Geometria,
    Materiais,
    Opcoes,
    Parede,
    gama_n,
    validar,
)


def parede(bx=300, by=20, hw=3.0, fck=30, G=None, Q=None, W=None, **op):
    return Parede(
        Geometria(bx=bx, by=by, hw=hw),
        Materiais(fck=fck),
        Acoes(
            G=G or Esforcos(N=100),
            Q=Q or Esforcos(),
            W=W or Esforcos(),
        ),
        Opcoes(**op),
    )


def chaves(combs):
    return {(round(c.fG, 3), round(c.fQ, 3), round(c.fW, 3)) for c in combs}


# Entrada e validações


def test_comprimento_e_espessura_independem_da_orientacao():
    a, b = parede(bx=300, by=20).geometria, parede(bx=20, by=300).geometria
    assert (a.lw, a.h, a.eixo_comprimento) == (300, 20, "X")
    assert (b.lw, b.h, b.eixo_comprimento) == (300, 20, "Y")


def test_mapeamento_no_plano_segue_o_eixo_do_comprimento():
    mx = mapeamento(parede(bx=300, by=20))
    assert (mx.M_no_plano, mx.V_no_plano, mx.M_fora_plano, mx.V_fora_plano) == ("My", "Vx", "Mx", "Vy")
    my = mapeamento(parede(bx=20, by=300))
    assert (my.M_no_plano, my.V_no_plano, my.M_fora_plano, my.V_fora_plano) == ("Mx", "Vy", "My", "Vx")


def test_zona_de_extremidade_padrao():
    assert parede(bx=300, by=20).le == pytest.approx(40)  # 2h governa
    assert parede(bx=600, by=20).le == pytest.approx(60)  # 0,10·lw governa
    assert parede(le=50).le == 50


def test_gama_n():
    assert gama_n(15) == pytest.approx(1.20)
    assert gama_n(19) == 1.0


def test_validacao_espessura():
    assert any(m.nivel == "erro" and m.campo == "h" for m in validar(parede(by=12)))
    avisos = [m for m in validar(parede(by=16)) if m.campo == "h"]
    assert avisos and avisos[0].nivel == "aviso"
    assert not validar(parede(by=20))


def test_validacao_fck_e_acoes():
    assert any(m.campo == "fck" for m in validar(parede(fck=95)))
    vazia = Parede(Geometria(300, 20, 3), Materiais(), Acoes())
    assert any(m.campo == "acoes" for m in validar(vazia))


def test_mensagens_bilingues():
    m = validar(parede(fck=95))[0]
    assert "fck" in m.texto.em("pt") and "outside" in m.texto.em("en")


# Combinações


def test_nbr_sem_vento():
    p = parede(G=Esforcos(N=100), Q=Esforcos(N=50))
    combs = combinacoes_nbr(p)
    assert chaves(combs) == {(1.4, 0, 0), (1.4, 1.4, 0), (1.0, 0, 0), (1.0, 1.4, 0)}
    normais = sorted(c.esforcos.N for c in combs)
    assert normais == pytest.approx([100, 140, 170, 210])


def test_nbr_com_vento_nos_dois_sentidos():
    p = parede(G=Esforcos(N=100), Q=Esforcos(N=50), W=Esforcos(My=10))
    ch = chaves(combinacoes_nbr(p))
    assert (1.4, 0.7, 1.4) in ch and (1.4, 0.7, -1.4) in ch  # W principal, ψ0 = 0,5
    assert (1.4, 1.4, 0.84) in ch and (1.0, 0, -1.4) in ch  # Q principal; G favorável


def test_nbr_aplica_gama_n():
    p = parede(by=15, G=Esforcos(N=100))
    assert max(c.esforcos.N for c in combinacoes_nbr(p)) == pytest.approx(1.4 * 1.2 * 100)


def test_aci_com_reducao_de_L():
    p = parede(G=Esforcos(N=100), Q=Esforcos(N=50), W=Esforcos(My=10))
    ch = chaves(combinacoes_aci(p))
    assert {(1.4, 0, 0), (1.2, 1.6, 0), (1.2, 0.5, 1.0), (1.2, 0.5, -1.0), (0.9, 0, 1.0), (0.9, 0, -1.0)} <= ch
    assert (1.2, 1.0, 1.0) not in ch


def test_aci_sem_reducao_de_L():
    p = parede(G=Esforcos(N=100), Q=Esforcos(N=50), W=Esforcos(My=10), aci_reducao_L=False)
    assert (1.2, 1.0, 1.0) in chaves(combinacoes_aci(p))


def test_expressao_legivel():
    p = parede(G=Esforcos(N=100), Q=Esforcos(N=50), W=Esforcos(My=10))
    exprs = {c.expressao for c in combinacoes_aci(p)}
    assert "1,2·D + 0,5·L + 1,0·W" in exprs and "0,9·D − 1,0·W" in exprs


# Classificação


def test_tipo_de_elemento():
    assert tipo_elemento(parede(bx=300, by=20)).resultado == "pilar-parede"
    assert tipo_elemento(parede(bx=100, by=25)).resultado == "pilar"


def test_regime_limite_hw_lw_igual_a_2():
    assert regime(parede(bx=300, hw=6.0)).resultado == "B"
    assert regime(parede(bx=300, hw=5.9)).resultado == "D"


def test_esbeltez():
    p = parede(bx=300, by=20, hw=3.0)
    assert lambda_fora_plano(p) == pytest.approx(51.9)
    comb = combinacoes_nbr(p)[0]
    assert esbeltez_nbr(p, comb).resultado == "pilar-padrao"  # λ1 = 35 sem excentricidade
    assert esbeltez_nbr(parede(hw=1.5), comb).resultado == "dispensada"
    assert esbeltez_nbr(parede(hw=6.0), comb).resultado == "fora-do-escopo"
    assert esbeltez_aci(p).resultado == "amplificacao"  # k·lu/r = 50


def test_solicitacao():
    p = parede(G=Esforcos(N=100, Mx=5, My=20))
    assert solicitacao(combinacoes_nbr(p)[0]).pt == "Flexo-compressão oblíqua"
    p = parede(G=Esforcos(N=-100, My=20))
    assert solicitacao(combinacoes_nbr(p)[0]).en == "Uniaxial bending with tension"
