"""Interface web da calculadora (Streamlit).

Rodar localmente:  streamlit run app.py
"""

import altair as alt
import pandas as pd
import streamlit as st

from calculadora_parede.aci318 import dimensionar_aci
from calculadora_parede.armadura import barras_parede
from calculadora_parede.classificacao import (
    esbeltez_aci,
    esbeltez_nbr,
    mapeamento,
    regime,
    tipo_elemento,
)
from calculadora_parede.entrada import (
    ACOS,
    Acoes,
    Esforcos,
    Geometria,
    Materiais,
    Opcoes,
    Parede,
    validar,
)
from calculadora_parede.materiais import ConcretoACI, ConcretoNBR, aco_aci, aco_nbr
from calculadora_parede.nbr6118 import dimensionar_nbr
from calculadora_parede.secao_fibras import Secao

st.set_page_config(page_title="Calculadora de Paredes Estruturais", page_icon="🧱", layout="wide")

COR_NBR, COR_ACI = "#0f7b6c", "#b26a12"
PSI0 = {"Residencial (ψ0 = 0,5)": 0.5, "Comercial / escritórios (ψ0 = 0,7)": 0.7, "Bibliotecas, garagens (ψ0 = 0,8)": 0.8}

idioma = st.sidebar.radio("Idioma / Language", ["PT", "EN"], horizontal=True)
EN = idioma == "EN"


def t(pt: str, en: str) -> str:
    return en if EN else pt


def num(v: float, casas: int = 2) -> str:
    txt = f"{v:,.{casas}f}"
    return txt if EN else txt.replace(",", "X").replace(".", ",").replace("X", ".")


st.title(t("Calculadora de Paredes Estruturais", "Structural Wall Calculator"))
st.caption(t(
    "Dimensionamento de paredes de concreto armado pela NBR 6118:2026 e pelo ACI 318-25. "
    "Eixos da seção: X horizontal, Y vertical; Mx positivo comprime a face inferior, My positivo comprime a face direita; compressão positiva.",
    "Reinforced concrete wall design per NBR 6118:2026 and ACI 318-25. "
    "Section axes: X horizontal, Y vertical; positive Mx compresses the bottom face, positive My compresses the right face; compression positive.",
))

# Entrada

with st.sidebar.form("entrada"):
    st.subheader(t("Geometria", "Geometry"))
    c1, c2 = st.columns(2)
    bx = c1.number_input(t("Largura bx (cm)", "Width bx (cm)"), 10.0, 5000.0, 300.0, 5.0, key="bx")
    by = c2.number_input(t("Profundidade by (cm)", "Depth by (cm)"), 10.0, 5000.0, 20.0, 1.0, key="by")
    hw = c1.number_input(t("Altura livre hw (m)", "Clear height hw (m)"), 0.5, 100.0, 3.0, 0.1, key="hw")
    k = c2.number_input(t("Coef. comprimento efetivo k", "Effective length factor k"), 0.5, 3.0, 1.0, 0.1, key="k")
    cob = c1.number_input(t("Cobrimento (mm)", "Cover (mm)"), 15.0, 80.0, 30.0, 5.0, key="cob")

    st.subheader(t("Materiais", "Materials"))
    c1, c2 = st.columns(2)
    fck = c1.number_input("fck (MPa)", 20.0, 90.0, 30.0, 5.0, key="fck")
    aco = c2.selectbox(t("Aço", "Steel"), list(ACOS), index=1, key="aco")

    st.subheader(t("Armadura", "Reinforcement"))
    le_auto = st.checkbox(t("Zona de extremidade automática: máx(0,10·lw; 2h)", "Automatic boundary zone: max(0.10·lw; 2h)"), True, key="le_auto")
    le = st.number_input(t("Zona de extremidade le (cm)", "Boundary zone le (cm)"), 5.0, 1000.0, 40.0, 5.0, key="le")
    c1, c2 = st.columns(2)
    phi_e = c1.selectbox(t("φ extremidade (mm)", "Boundary φ (mm)"), [10.0, 12.5, 16.0, 20.0, 25.0, 32.0], index=2, key="phi_e")
    phi_a = c2.selectbox(t("φ alma (mm)", "Web φ (mm)"), [6.3, 8.0, 10.0, 12.5, 16.0], index=2, key="phi_a")

    st.subheader(t("Esforços característicos", "Characteristic loads"))
    st.caption(t("kN e kN·m. Vento testado nos dois sentidos.", "kN and kN·m. Wind checked in both directions."))
    abas = st.tabs([t("Permanente G", "Dead G"), t("Variável Q", "Live Q"), t("Vento W", "Wind W")])
    padroes = {"G": (800.0, 4.0, 150.0, 10.0, 0.0), "Q": (300.0, 2.0, 60.0, 0.0, 0.0), "W": (0.0, 0.0, 1800.0, 300.0, 0.0)}
    acoes = {}
    for aba, nome in zip(abas, ("G", "Q", "W")):
        with aba:
            vals = []
            cols = st.columns(2)
            for i, rot in enumerate(("N", "Mx", "My", "Vx", "Vy")):
                vals.append(cols[i % 2].number_input(rot, value=padroes[nome][i], step=10.0, key=f"{nome}_{rot}"))
            acoes[nome] = Esforcos(*vals)

    st.subheader(t("Opções", "Options"))
    uso = st.selectbox(t("Uso da edificação (NBR)", "Building use (NBR)"), list(PSI0), key="uso")
    red_L = st.checkbox(t("ACI 5.3.3: usar 0,5·L com vento", "ACI 5.3.3: use 0.5·L with wind"), True, key="red_L",
                        help=t("Não vale para garagens, áreas de reunião pública ou L > 4,8 kN/m².",
                               "Not allowed for garages, public assembly areas or L > 4.8 kN/m²."))
    calcular = st.form_submit_button(t("Calcular", "Calculate"), type="primary", width="stretch")

parede = Parede(
    Geometria(bx, by, hw, k, cob),
    Materiais(fck, aco),
    Acoes(**acoes),
    Opcoes(psi0=PSI0[uso], aci_reducao_L=red_L, le=None if le_auto else le, phi_extremidade=phi_e, phi_alma=phi_a),
)

if not calcular and "resultado" not in st.session_state:
    st.info(t("Os campos estão preenchidos com um exemplo. Ajuste os dados à esquerda e clique em Calcular.",
              "Fields hold an example. Adjust the data on the left and click Calculate."))
    st.stop()

msgs = validar(parede)
for m in msgs:
    (st.error if m.nivel == "erro" else st.warning)(m.texto.em("en" if EN else "pt"))
if any(m.nivel == "erro" for m in msgs):
    st.stop()


@st.cache_data(show_spinner=False)
def calcular_tudo(p: Parede):
    return dimensionar_nbr(p), dimensionar_aci(p)


if calcular:
    with st.spinner(t("Dimensionando pelas duas normas…", "Designing per both codes…")):
        st.session_state["resultado"] = (parede, *calcular_tudo(parede))
p, rn, ra = st.session_state["resultado"]
lg = "en" if EN else "pt"

# Metodologia

st.header(t("Metodologia", "Method"))
mp = mapeamento(p)
c0 = rn.combinacoes[0].comb
itens = [
    t(f"Parede ao longo de {mp.eixo_comprimento}: {mp.M_no_plano} e {mp.V_no_plano} no plano; {mp.M_fora_plano} e {mp.V_fora_plano} fora do plano.",
      f"Wall along {mp.eixo_comprimento}: {mp.M_no_plano} and {mp.V_no_plano} in-plane; {mp.M_fora_plano} and {mp.V_fora_plano} out-of-plane."),
    tipo_elemento(p).texto.em(lg),
    regime(p).texto.em(lg),
    "NBR: " + esbeltez_nbr(p, c0).texto.em(lg),
    "ACI: " + esbeltez_aci(p).texto.em(lg),
]
st.markdown("\n".join(f"- {i}" for i in itens))

# Resultado lado a lado

st.header(t("Resultado", "Result"))
for nome, r in (("NBR", rn), ("ACI", ra)):
    for m in r.mensagens:
        (st.error if m.nivel == "erro" else st.warning)(f"{nome}: {m.texto.em(lg)}")


def linha(r):
    est = r.estribos_extremidade if not EN else r.estribos_extremidade.replace("não exigidos", "not required")
    return [
        f"{num(r.As_extremidade)} cm² → {r.barras_extremidade}",
        est,
        f"{num(r.As_alma_face)} cm²/m → {r.barras_alma}",
        f"{num(r.As_horizontal_face)} cm²/m → {r.barras_horizontal}",
        f"{num(r.grampos_fora_plano)} cm²/m²" if r.grampos_fora_plano else t("dispensados", "not required"),
        num(r.util_flexao),
        num(r.util_cortante),
        r.comb_flexao,
        r.governa.em(lg),
    ]


rotulos = [
    t("Cada zona de extremidade", "Each boundary zone"),
    t("Estribos da extremidade", "Boundary ties"),
    t("Vertical da alma, por face", "Web vertical, per face"),
    t("Horizontal, por face", "Horizontal, per face"),
    t("Grampos fora do plano", "Out-of-plane cross-ties"),
    t("Utilização à flexão", "Flexure utilization"),
    t("Utilização ao cortante", "Shear utilization"),
    t("Combinação que governa a flexão", "Combination governing flexure"),
    t("Governa", "Governs"),
]
st.dataframe(
    pd.DataFrame({"NBR 6118:2026": linha(rn), "ACI 318-25": linha(ra)}, index=rotulos),
    width="stretch",
)

# Seção e diagramas


def secao_obj(r, norma):
    g = p.geometria
    b = barras_parede(g.bx / 100, g.by / 100, g.cobrimento / 1000, p.le / 100,
                      r.As_extremidade / 1e4, r.As_alma_face / 1e4)
    if norma == "NBR":
        return Secao(g.bx / 100, g.by / 100, b, ConcretoNBR(p.materiais.fck), aco_nbr(p.materiais.fyk)), b
    return Secao(g.bx / 100, g.by / 100, b, ConcretoACI(p.materiais.fck), aco_aci(p.materiais.fyk)), b


s_nbr, b_nbr = secao_obj(rn, "NBR")
s_aci, b_aci = secao_obj(ra, "ACI")

st.subheader(t("Seção com a armadura da NBR", "Section with NBR reinforcement"))
g = p.geometria
contorno = pd.DataFrame({"x": [-g.bx / 200, g.bx / 200, g.bx / 200, -g.bx / 200, -g.bx / 200],
                         "y": [-g.by / 200, -g.by / 200, g.by / 200, g.by / 200, -g.by / 200], "o": range(5)})
barras_df = pd.DataFrame({"x": [b.x for b in b_nbr], "y": [b.y for b in b_nbr], "area_cm2": [b.area * 1e4 for b in b_nbr]})
dom = [-max(g.bx, g.by) / 200 * 1.05, max(g.bx, g.by) / 200 * 1.05]
graf_secao = (
    alt.Chart(contorno).mark_line(color="#16222a").encode(x=alt.X("x", scale=alt.Scale(domain=dom), title="X (m)"), y=alt.Y("y", scale=alt.Scale(domain=dom), title="Y (m)"), order="o")
    + alt.Chart(barras_df).mark_circle(color="#16222a").encode(x="x", y="y", size=alt.Size("area_cm2", legend=None), tooltip=["x", "y", "area_cm2"])
).properties(height=320)
st.altair_chart(graf_secao, width="stretch")


def diagrama(eixo: str):
    linhas = []
    for norma, s in (("NBR", s_nbr), ("ACI", s_aci)):
        d = s.diagrama(eixo, 80)
        pos, neg = d["positivo"], d["negativo"][::-1]
        for i, (N, M) in enumerate(list(pos) + list(neg)):
            linhas.append({"norma": norma, "N": N, "M": M, "o": i})
    combs = [{"norma": "NBR", "N": c.Nd, "M": c.Mxd if eixo == "x" else c.Myd, "comb": c.comb.expressao} for c in rn.combinacoes]
    combs += [{"norma": "ACI", "N": c.Pu, "M": c.Mux if eixo == "x" else c.Muy, "comb": c.comb.expressao} for c in ra.combinacoes]
    cor = alt.Color("norma", scale=alt.Scale(domain=["NBR", "ACI"], range=[COR_NBR, COR_ACI]), title=None)
    rot = "Mx" if eixo == "x" else "My"
    return (
        alt.Chart(pd.DataFrame(linhas)).mark_line().encode(x=alt.X("M", title=f"{rot} (kN·m)"), y=alt.Y("N", title="N (kN)"), color=cor, order="o")
        + alt.Chart(pd.DataFrame(combs)).mark_circle(size=50).encode(x="M", y="N", color=cor, tooltip=["norma", "comb", "N", "M"])
    ).properties(height=380)


c1, c2 = st.columns(2)
with c1:
    st.subheader(t("N × My", "N × My"))
    st.altair_chart(diagrama("y"), width="stretch")
with c2:
    st.subheader(t("N × Mx", "N × Mx"))
    st.altair_chart(diagrama("x"), width="stretch")

# Combinações

st.header(t("Combinações", "Load combinations"))
c1, c2 = st.columns(2)
with c1:
    st.subheader("NBR 6118")
    st.dataframe(pd.DataFrame([{
        t("Combinação", "Combination"): c.comb.expressao, "Nd": round(c.Nd, 1), "Mxd": round(c.Mxd, 1), "Myd": round(c.Myd, 1),
        "M2d": round(c.segunda_ordem, 1), t("Utilização", "Utilization"): round(c.utilizacao, 3),
    } for c in rn.combinacoes]), width="stretch", hide_index=True)
with c2:
    st.subheader("ACI 318")
    st.dataframe(pd.DataFrame([{
        t("Combinação", "Combination"): c.comb.expressao, "Pu": round(c.Pu, 1), "Mux": round(c.Mux, 1), "Muy": round(c.Muy, 1),
        "δ": round(c.delta, 3), t("Utilização", "Utilization"): round(c.utilizacao, 3),
    } for c in ra.combinacoes]), width="stretch", hide_index=True)

# Memorial

st.header(t("Memorial de cálculo", "Calculation report"))


def memorial_md(r, titulo):
    partes = [f"## {titulo}\n"]
    for i, ps in enumerate(r.memorial.passos, 1):
        partes.append(f"### {i}. {ps.titulo.em(lg)}\n\n$$\n{ps.simbolica}\n$$\n\n$$\n{ps.valores}\n$$\n\n$$\n{ps.resultado}\n$$\n\n*{ps.item}*\n")
    return "\n".join(partes)


for r, titulo in ((rn, "NBR 6118:2026"), (ra, "ACI 318-25")):
    with st.expander(titulo):
        for i, ps in enumerate(r.memorial.passos, 1):
            st.markdown(f"**{i}. {ps.titulo.em(lg)}**")
            st.latex(ps.simbolica)
            st.latex(ps.valores)
            st.latex(ps.resultado)
            st.caption(ps.item)

st.download_button(
    t("Baixar memorial (Markdown)", "Download report (Markdown)"),
    memorial_md(rn, "NBR 6118:2026") + "\n" + memorial_md(ra, "ACI 318-25"),
    file_name="memorial-parede.md",
)
