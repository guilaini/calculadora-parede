"""Dimensionamento da parede pelo ACI 318-25.

Mesmo roteiro da NBR, com as regras do ACI: amplificação de momentos para a
esbeltez fora do plano (6.6.4), armadura das extremidades por busca na
superfície φ·(Pn, Mnx, Mny), cortante no plano pelo Capítulo 11 (11.5.4),
bielas e tirantes (Cap. 23) na parede baixa, cortante fora do plano (22.5) e
mínimos de parede (11.6). Unidades internas em kN e m; tensões em MPa.
"""

import math
from dataclasses import dataclass, field

from . import armadura as arm
from .classificacao import esbeltez_aci, mapeamento, regime
from .combinacoes import Combinacao, combinacoes_aci
from .entrada import Parede
from .materiais import ConcretoACI, aco_aci
from .memorial import Memorial, n
from .secao_fibras import Secao
from .textos import Mensagem, Texto

PHI_V = 0.75


@dataclass
class CombinacaoCalculoACI:
    comb: Combinacao
    Pu: float
    Mux: float
    Muy: float
    V_no_plano: float
    V_fora_plano: float
    delta: float = 1.0
    utilizacao: float = 0.0


@dataclass
class ResultadoACI:
    norma: str = "ACI 318-25"
    As_extremidade: float = 0.0  # cm², por zona (duas faces)
    barras_extremidade: str = ""
    estribos_extremidade: str = ""
    As_alma_face: float = 0.0  # cm²/m por face
    barras_alma: str = ""
    As_horizontal_face: float = 0.0  # cm²/m por face
    barras_horizontal: str = ""
    grampos_fora_plano: float = 0.0  # cm²/m²
    util_flexao: float = 0.0
    util_cortante: float = 0.0
    comb_flexao: str = ""
    comb_cortante: str = ""
    governa: Texto = field(default_factory=lambda: Texto("", ""))
    combinacoes: list[CombinacaoCalculoACI] = field(default_factory=list)
    mensagens: list[Mensagem] = field(default_factory=list)
    memorial: Memorial = field(default_factory=Memorial)


def _alpha_c(hw_lw: float) -> float:
    """αc (11.5.4.3): 0,25 para hw/lw ≤ 1,5; 0,17 para hw/lw ≥ 2,0; linear entre os dois."""
    if hw_lw <= 1.5:
        return 0.25
    if hw_lw >= 2.0:
        return 0.17
    return 0.25 + (0.17 - 0.25) * (hw_lw - 1.5) / 0.5


def dimensionar_aci(parede: Parede) -> ResultadoACI:
    r = ResultadoACI()
    mem = r.memorial
    g, mat, op = parede.geometria, parede.materiais, parede.opcoes
    mp = mapeamento(parede)
    lw, h = g.lw / 100, g.h / 100
    le = parede.le / 100
    Ag = lw * h
    fc, fy = mat.fck, mat.fyk  # f'c = fck adotado
    conc, aco = ConcretoACI(fc), aco_aci(fy)
    raiz = math.sqrt(fc)
    c_m = g.cobrimento / 1000
    hw_lw = g.hw / lw

    mem.add(
        "Materiais: f'c = fck e fy = fyk; bloco retangular equivalente",
        "Materials: f'c = fck and fy = fyk; equivalent rectangular block",
        r"\beta_1 = 0{,}85 - 0{,}05\,\frac{f'_c - 28}{7} \quad (0{,}65 \le \beta_1 \le 0{,}85)",
        rf"f'_c = {n(fc, 0)}\ MPa \qquad f_y = {n(fy, 0)}\ MPa",
        rf"\beta_1 = {n(conc.beta1, 3)}",
        "ACI 318-25, 22.2.2.4.3",
    )

    # 1. Esforços de cálculo com amplificação de momentos fora do plano
    esb = esbeltez_aci(parede).resultado
    Ec = 4700 * raiz  # MPa
    Ig_out = lw * h**3 / 12
    calc: list[CombinacaoCalculoACI] = []
    instavel = False
    for comb in combinacoes_aci(parede):
        sep = mp.separar(comb.esforcos)
        Pu = sep["N"]
        M_in, M_out = sep["M_no_plano"], sep["M_fora_plano"]
        delta = 1.0
        if Pu > 0 and esb == "amplificacao":
            M_out = math.copysign(max(abs(M_out), Pu * (0.015 + 0.03 * h)), M_out or 1.0)
            Pd = comb.fG * parede.acoes.G.N
            beta_dns = min(max(Pd / Pu, 0.0), 1.0) if Pu > 0 else 0.0
            EI = 0.4 * Ec * 1e3 * Ig_out / (1 + beta_dns)  # kN·m²
            Pc = math.pi**2 * EI / (g.k * g.hw) ** 2
            if Pu >= 0.75 * Pc:
                instavel = True
                delta = math.inf
            else:
                delta = max(1.0, 1.0 / (1 - Pu / (0.75 * Pc)))
                M_out *= delta
        Mux, Muy = (M_out, M_in) if mp.M_no_plano == "My" else (M_in, M_out)
        calc.append(CombinacaoCalculoACI(comb, Pu, Mux, Muy, abs(sep["V_no_plano"]), abs(sep["V_fora_plano"]), delta))
    r.combinacoes = calc
    if instavel:
        r.mensagens.append(Mensagem(
            "erro", "esbeltez",
            Texto("Pu ≥ 0,75·Pc: a parede é instável fora do plano (6.6.4.5). Aumente a espessura.",
                  "Pu ≥ 0.75·Pc: the wall is unstable out of plane (6.6.4.5). Increase thickness."),
        ))
        calc = [c for c in calc if math.isfinite(c.delta)]
    amp = [c for c in calc if c.delta > 1.0]
    if amp:
        c1 = max(amp, key=lambda c: c.delta)
        mem.add(
            "Amplificação de momentos fora do plano (estrutura indeslocável, Cm = 1,0)",
            "Out-of-plane moment magnification (nonsway, Cm = 1.0)",
            r"\delta = \frac{C_m}{1 - \dfrac{P_u}{0{,}75\,P_c}} \ge 1 \qquad P_c = \frac{\pi^2\,(EI)_{eff}}{(k\,\ell_u)^2} \qquad (EI)_{eff} = \frac{0{,}4\,E_c\,I_g}{1 + \beta_{dns}}",
            rf"P_u = {n(c1.Pu, 1)}\ kN \qquad E_c = 4700\sqrt{{f'_c}} = {n(Ec, 0)}\ MPa",
            rf"\delta = {n(c1.delta, 3)}",
            "ACI 318-25, 6.6.4.5",
        )

    # 2. Cortante no plano e taxas mínimas (definem a alma)
    Acv = h * lw
    ac = _alpha_c(hw_lw)
    Vn_max = 0.66 * raiz * Acv * 1e3
    Vc_in = ac * raiz * Acv * 1e3
    gov_v = max(calc, key=lambda c: c.V_no_plano)
    Vu = gov_v.V_no_plano
    rho_t_calc = max(0.0, (Vu / PHI_V - Vc_in) / (fy * 1e3 * Acv))
    barra_fina = op.phi_alma <= 16 and fy >= 420
    cortante_alto = Vu > 0.5 * PHI_V * Vc_in
    if cortante_alto:
        rho_t_min, rho_l_min = 0.0025, 0.0025
    else:
        rho_t_min = 0.0020 if barra_fina else 0.0025
        rho_l_min = 0.0012 if barra_fina else 0.0015
    rho_t = max(rho_t_calc, rho_t_min)
    if cortante_alto:  # 11.6.2: não precisa exceder ρt
        rho_l_min = min(max(0.0025, 0.0025 + 0.5 * (2.5 - hw_lw) * (rho_t - 0.0025)), rho_t)

    s_max = min(3 * g.h, 45.0)  # cm
    As_h_face = rho_t * h / 2  # m²/m por face
    r.As_horizontal_face = As_h_face * 1e4
    s_h, _ = arm.espacamento(r.As_horizontal_face, op.phi_alma, min(s_max, lw * 100 / 5 if cortante_alto else s_max))
    r.barras_horizontal = f"φ{op.phi_alma:g} c/ {s_h:g} cm".replace(".", ",")
    r.util_cortante = Vu / (PHI_V * min(Vn_max, (ac * raiz + rho_t * fy) * Acv * 1e3)) if Vu > 0 else 0.0
    r.comb_cortante = f"{gov_v.comb.nome}: {gov_v.comb.expressao}"

    mem.add(
        "Cortante no plano da parede",
        "In-plane wall shear",
        r"V_n = \left(\alpha_c\,\lambda\,\sqrt{f'_c} + \rho_t\,f_{yt}\right)A_{cv} \le 0{,}66\,\sqrt{f'_c}\,A_{cv} \qquad \phi = 0{,}75",
        rf"\alpha_c = {n(ac, 3)}\ (h_w/\ell_w = {n(hw_lw)}) \qquad A_{{cv}} = {n(Acv, 3)}\ m^2 \qquad V_u = {n(Vu, 1)}\ kN",
        rf"\rho_t = {n(rho_t, 4)}\ (\text{{calc. }} {n(rho_t_calc, 4)},\ \text{{mín. }} {n(rho_t_min, 4)}) \qquad 0{{,}}66\sqrt{{f'_c}}A_{{cv}} = {n(Vn_max, 1)}\ kN",
        "ACI 318-25, 11.5.4 e 11.6",
    )
    if Vu > PHI_V * Vn_max:
        r.mensagens.append(Mensagem(
            "erro", "cortante",
            Texto(f"Vu acima de φ·0,66·√f'c·Acv = {PHI_V * Vn_max:.0f} kN (11.5.4). Aumente a espessura ou o f'c.",
                  f"Vu exceeds φ·0.66·√f'c·Acv = {PHI_V * Vn_max:.0f} kN (11.5.4). Increase thickness or f'c."),
        ))

    # 3. Armadura das zonas de extremidade
    As_alma_face = rho_l_min * h / 2  # m²/m por face
    tam = max(0.01, lw / 150)

    def secao(As_ext: float) -> Secao:
        barras = arm.barras_parede(
            g.bx / 100, g.by / 100, c_m, le, As_ext, As_alma_face,
            op.phi_extremidade / 1000, op.phi_alma / 1000,
        )
        return Secao(g.bx / 100, g.by / 100, barras, conc, aco, tamanho_fibra=tam)

    def util_max(As_ext: float) -> tuple[float, list[float]]:
        s = secao(As_ext)
        us = [s.utilizacao(c.Pu, c.Mux, c.Muy, 36, 121) for c in calc]
        return max(us), us

    As_min_ext = rho_l_min * le * h
    As_max_ext = 0.04 * le * h
    if util_max(As_min_ext)[0] <= 1.0:
        As_ext = As_min_ext
    elif util_max(As_max_ext)[0] > 1.0:
        As_ext = As_max_ext
        r.mensagens.append(Mensagem(
            "erro", "flexao",
            Texto("Seção insuficiente à flexo-compressão: mesmo com 4% na zona de extremidade não atende. Aumente a espessura, o comprimento ou o f'c.",
                  "Section inadequate for axial load and bending even with 4% in the boundary zone. Increase thickness, length or f'c."),
        ))
    else:
        lo, hi = As_min_ext, As_max_ext
        for _ in range(12):
            mid = 0.5 * (lo + hi)
            if util_max(mid)[0] > 1.0:
                lo = mid
            else:
                hi = mid
        As_ext = hi
    _, us = util_max(As_ext)
    for c, u in zip(calc, us):
        c.utilizacao = u
    gov_f = max(calc, key=lambda c: c.utilizacao)
    r.util_flexao = gov_f.utilizacao
    r.comb_flexao = f"{gov_f.comb.nome}: {gov_f.comb.expressao}"

    n_b, As_real = arm.barras_zona(As_ext * 1e4, op.phi_extremidade)
    r.As_extremidade = As_ext * 1e4
    r.barras_extremidade = f"{n_b} φ{op.phi_extremidade:g} ({n(As_real).replace('{,}', ',')} cm²)"
    r.As_alma_face = As_alma_face * 1e4
    s_v, _ = arm.espacamento(r.As_alma_face, op.phi_alma, min(s_max, lw * 100 / 3 if cortante_alto else s_max))
    r.barras_alma = f"φ{op.phi_alma:g} c/ {s_v:g} cm".replace(".", ",")

    rho_zona = As_real / 1e4 / (le * h)
    if rho_zona > 0.01:
        phi_tie = 10.0 if op.phi_extremidade <= 32 else 12.5
        s_tie = min(16 * op.phi_extremidade / 10, 48 * phi_tie / 10, g.h)
        r.estribos_extremidade = f"φ{phi_tie:g} c/ {math.floor(s_tie):g} cm"
    else:
        r.estribos_extremidade = "não exigidos (ρ ≤ 1%)"

    mem.add(
        "Armadura das zonas de extremidade (busca na superfície φPn–φMnx–φMny)",
        "Boundary zone steel (search on the φPn–φMnx–φMny surface)",
        r"\max_{comb}\ \eta(P_u, M_{ux}, M_{uy};\ A_{s,ext}) \le 1 \qquad \phi = 0{,}65 \ldots 0{,}90",
        rf"P_u = {n(gov_f.Pu, 1)}\ kN,\ M_{{ux}} = {n(gov_f.Mux, 1)}\ kN \cdot m,\ M_{{uy}} = {n(gov_f.Muy, 1)}\ kN \cdot m",
        rf"A_{{s,ext}} = {n(As_ext * 1e4)}\ cm^2 \ (\eta = {n(gov_f.utilizacao, 3)})",
        "ACI 318-25, 22.4 e 21.2.2",
    )
    sinal = ">" if cortante_alto else r"\le"
    mem.add(
        "Taxas mínimas de parede",
        "Minimum wall reinforcement ratios",
        r"\rho_\ell \ge 0{,}0025 + 0{,}5\,(2{,}5 - h_w/\ell_w)(\rho_t - 0{,}0025) \quad \text{(cortante alto)}",
        rf"V_u = {n(Vu, 1)}\ kN\ {sinal}\ 0{{,}}5\,\phi\,\alpha_c\sqrt{{f'_c}}A_{{cv}} = {n(0.5 * PHI_V * Vc_in, 1)}\ kN",
        rf"\rho_\ell = {n(rho_l_min, 4)} \qquad \rho_t = {n(rho_t, 4)}",
        "ACI 318-25, 11.6.1 e 11.6.2",
    )

    # Parede baixa: biela diagonal (Cap. 23)
    if regime(parede).resultado == "D" and Vu > 0:
        z = lw - le
        theta = math.atan2(g.hw, z)
        C = Vu / math.cos(theta)
        w = le * math.sin(theta)
        fce = 0.85 * 0.75 * fc  # βs = 0,75, βc = 1,0
        phiFns = PHI_V * fce * w * h * 1e3
        r.util_cortante = max(r.util_cortante, C / phiFns)
        mem.add(
            "Bielas e tirantes: biela diagonal principal",
            "Strut-and-tie: main diagonal strut",
            r"F_{us} = \frac{V_u}{\cos\theta} \le \phi\,F_{ns} = \phi\,(0{,}85\,\beta_c\,\beta_s\,f'_c)\,w\,h",
            rf"\theta = {n(math.degrees(theta), 1)}^\circ \qquad w = {n(w, 3)}\ m \qquad \beta_s = 0{{,}}75",
            rf"F_{{us}} = {n(C, 1)}\ kN \le \phi F_{{ns}} = {n(phiFns, 1)}\ kN",
            "ACI 318-25, 23.4",
        )
        if C > phiFns:
            r.mensagens.append(Mensagem(
                "erro", "biela",
                Texto("A biela diagonal da parede baixa excede φFns (23.4). Aumente a espessura, a zona de extremidade ou o f'c.",
                      "The squat wall diagonal strut exceeds φFns (23.4). Increase thickness, boundary zone or f'c."),
            ))

    # 4. Cortante fora do plano (22.5.5.1)
    phi_t = 10.0
    d_out = h - c_m - phi_t / 1000 - op.phi_extremidade / 2000
    As_tot = 2 * As_ext + 2 * As_alma_face * max(lw - 2 * le, 0)
    rho_w = (As_tot / 2) / (lw * d_out)
    lam_s = min(1.0, math.sqrt(2 / (1 + 0.004 * d_out * 1000)))
    gov_o = max(calc, key=lambda c: c.V_fora_plano)
    Nu_Ag = min(max(gov_o.Pu, 0.0) / Ag / 1e3 / 6, 0.05 * fc)
    Vc_out = min((0.66 * lam_s * rho_w ** (1 / 3) * raiz + Nu_Ag), 0.42 * raiz) * lw * d_out * 1e3
    mem.add(
        "Cortante fora do plano, sem armadura transversal",
        "Out-of-plane shear, without shear reinforcement",
        r"V_c = \left[0{,}66\,\lambda_s\,\lambda\,\rho_w^{1/3}\sqrt{f'_c} + \frac{N_u}{6\,A_g}\right]b_w\,d \qquad \lambda_s = \sqrt{\frac{2}{1 + 0{,}004\,d}} \le 1",
        rf"\lambda_s = {n(lam_s, 3)},\ \rho_w = {n(rho_w, 4)},\ d = {n(d_out * 1000, 0)}\ mm",
        rf"\phi V_c = {n(PHI_V * Vc_out, 1)}\ kN\ \ (V_u = {n(gov_o.V_fora_plano, 1)}\ kN)",
        "ACI 318-25, 22.5.5.1",
    )
    if gov_o.V_fora_plano > PHI_V * Vc_out:
        Av_s = (gov_o.V_fora_plano / PHI_V - Vc_out) / (fy * 1e3 * d_out)
        r.grampos_fora_plano = Av_s / lw * 1e4
        r.mensagens.append(Mensagem(
            "aviso", "cortante_fora",
            Texto(f"Cortante fora do plano acima de φVc: prever grampos de {r.grampos_fora_plano:.2f} cm²/m por metro de parede.",
                  f"Out-of-plane shear exceeds φVc: provide cross-ties of {r.grampos_fora_plano:.2f} cm²/m per metre of wall."),
        ))
    r.util_cortante = max(r.util_cortante, gov_o.V_fora_plano / (PHI_V * Vc_out) if Vc_out > 0 else 0.0)

    if g.h > 25:
        r.mensagens.append(Mensagem(
            "aviso", "camadas",
            Texto("Espessura acima de 25 cm: armadura em duas camadas é obrigatória (11.7.2.3), como já adotado.",
                  "Thickness above 250 mm: two curtains required (11.7.2.3), as already adopted."),
        ))

    r.governa = Texto("Flexão", "Flexure") if r.util_flexao >= r.util_cortante else Texto("Cortante", "Shear")
    if As_ext <= As_min_ext * 1.0001:
        r.governa = Texto("Armadura mínima", "Minimum steel")
    return r
