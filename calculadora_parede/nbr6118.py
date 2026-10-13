"""Dimensionamento da parede pela NBR 6118:2026.

Roteiro: combinações → momentos mínimos e 2ª ordem local → armadura das zonas
de extremidade por busca na superfície de interação → cortante no plano
(treliça de Mörsch, Modelo I) ou bielas e tirantes → cortante fora do plano →
mínimos e detalhamento. Cada equação usada é registrada no memorial.
"""

import math
from dataclasses import dataclass, field

from . import armadura as arm
from .classificacao import esbeltez_nbr, mapeamento, regime
from .combinacoes import Combinacao, combinacoes_nbr
from .entrada import Parede
from .materiais import ConcretoNBR, aco_nbr
from .memorial import Memorial, n
from .secao_fibras import Secao
from .textos import Mensagem, Texto

TOL_UTIL = 1.0
FYWD_MAX = 435.0  # MPa, limite de fywd para estribos (17.4.2.2)


@dataclass
class CombinacaoCalculo:
    comb: Combinacao
    Nd: float
    Mxd: float
    Myd: float
    V_no_plano: float
    V_fora_plano: float
    segunda_ordem: float = 0.0  # kN·m somado fora do plano
    utilizacao: float = 0.0


@dataclass
class ResultadoNBR:
    norma: str = "NBR 6118:2026"
    As_extremidade: float = 0.0  # cm², por zona (duas faces)
    barras_extremidade: str = ""
    estribos_extremidade: str = ""
    As_alma_face: float = 0.0  # cm²/m por face
    barras_alma: str = ""
    As_horizontal_face: float = 0.0  # cm²/m por face
    barras_horizontal: str = ""
    grampos_fora_plano: float = 0.0  # cm²/m², 0 se dispensados
    util_flexao: float = 0.0
    util_cortante: float = 0.0
    comb_flexao: str = ""
    comb_cortante: str = ""
    governa: Texto = field(default_factory=lambda: Texto("", ""))
    combinacoes: list[CombinacaoCalculo] = field(default_factory=list)
    mensagens: list[Mensagem] = field(default_factory=list)
    memorial: Memorial = field(default_factory=Memorial)


def _fctm(fck: float) -> float:
    return 0.3 * fck ** (2 / 3) if fck <= 50 else 2.12 * math.log(1 + 0.11 * fck)


def dimensionar_nbr(parede: Parede) -> ResultadoNBR:
    r = ResultadoNBR()
    mem = r.memorial
    g, mat, op = parede.geometria, parede.materiais, parede.opcoes
    mp = mapeamento(parede)
    lw, h = g.lw / 100, g.h / 100  # m
    le = parede.le / 100
    Ac = lw * h
    conc, aco = ConcretoNBR(mat.fck), aco_nbr(mat.fyk)
    fcd, fyd = conc.fcd, aco.fy
    fywd = min(fyd, FYWD_MAX)
    c_m = g.cobrimento / 1000

    mem.add(
        "Resistências de cálculo",
        "Design strengths",
        r"f_{cd} = \frac{f_{ck}}{\gamma_c} \qquad f_{yd} = \frac{f_{yk}}{\gamma_s}",
        rf"f_{{cd}} = \frac{{{n(mat.fck, 0)}}}{{1{{,}}4}} \qquad f_{{yd}} = \frac{{{n(mat.fyk, 0)}}}{{1{{,}}15}}",
        rf"f_{{cd}} = {n(fcd)}\ MPa \qquad f_{{yd}} = {n(fyd)}\ MPa",
        "NBR 6118, 12.3.3 e 12.4",
    )

    # 1. Esforços de cálculo com momento mínimo e 2ª ordem local
    calc: list[CombinacaoCalculo] = []
    for comb in combinacoes_nbr(parede):
        sep = mp.separar(comb.esforcos)
        Nd = sep["N"]
        M_in, M_out = sep["M_no_plano"], sep["M_fora_plano"]
        M2 = 0.0
        if Nd > 0:
            M_in = math.copysign(max(abs(M_in), Nd * (0.015 + 0.03 * lw)), M_in or 1.0)
            M_out = math.copysign(max(abs(M_out), Nd * (0.015 + 0.03 * h)), M_out or 1.0)
            if esbeltez_nbr(parede, comb).resultado == "pilar-padrao":
                nu = Nd / (Ac * fcd * 1e3)
                inv_r = min(0.005 / (h * (nu + 0.5)), 0.005 / h)
                l_e = g.k * g.hw
                M2 = Nd * l_e**2 / 10 * inv_r
                M_out = math.copysign(abs(M_out) + M2, M_out)
        Mxd, Myd = (M_out, M_in) if mp.M_no_plano == "My" else (M_in, M_out)
        calc.append(
            CombinacaoCalculo(comb, Nd, Mxd, Myd, abs(sep["V_no_plano"]), abs(sep["V_fora_plano"]), M2)
        )
    r.combinacoes = calc

    Nmax = max((c.Nd for c in calc), default=0.0)
    gov_m = max(calc, key=lambda c: c.Nd)
    mem.add(
        "Momento mínimo de 1ª ordem (fora do plano)",
        "Minimum first-order moment (out-of-plane)",
        r"M_{1d,min} = N_d\,(0{,}015 + 0{,}03\,h)",
        rf"M_{{1d,min}} = {n(gov_m.Nd, 1)}\,(0{{,}}015 + 0{{,}}03 \cdot {n(h, 2)})",
        rf"M_{{1d,min}} = {n(gov_m.Nd * (0.015 + 0.03 * h))}\ kN \cdot m",
        "NBR 6118, 11.3.3.4.3",
    )
    com_2a = [c for c in calc if c.segunda_ordem > 0]
    if com_2a:
        c2 = max(com_2a, key=lambda c: c.segunda_ordem)
        nu = c2.Nd / (Ac * fcd * 1e3)
        mem.add(
            "Efeito local de 2ª ordem, pilar-padrão com curvatura aproximada",
            "Local second-order effect, model column with approximate curvature",
            r"M_{2d} = N_d\,\frac{\ell_e^2}{10}\,\frac{1}{r} \qquad \frac{1}{r} = \frac{0{,}005}{h\,(\nu + 0{,}5)} \le \frac{0{,}005}{h}",
            rf"\nu = {n(nu, 3)} \qquad \ell_e = {n(g.k * g.hw)}\ m",
            rf"M_{{2d}} = {n(c2.segunda_ordem)}\ kN \cdot m",
            "NBR 6118, 15.8.3.3.2 e 15.9",
        )

    # 2. Armadura das zonas de extremidade
    As_alma_face = 0.002 * h  # m²/m por face: 0,4% da alma nas duas faces
    tam = max(0.01, lw / 150)

    def secao(As_ext: float) -> Secao:
        barras = arm.barras_parede(
            g.bx / 100, g.by / 100, c_m, le, As_ext, As_alma_face,
            op.phi_extremidade / 1000, op.phi_alma / 1000,
        )
        return Secao(g.bx / 100, g.by / 100, barras, conc, aco, tamanho_fibra=tam)

    def util_max(As_ext: float) -> tuple[float, list[float]]:
        s = secao(As_ext)
        us = [s.utilizacao(c.Nd, c.Mxd, c.Myd, 36, 121) for c in calc]
        return max(us), us

    As_alma_total = 2 * As_alma_face * max(lw - 2 * le, 0.0)
    As_min_total = max(0.004 * Ac, 0.15 * Nmax / (fyd * 1e3))
    As_min_ext = max(0.004 * le * h, (As_min_total - As_alma_total) / 2)
    As_max_ext = 0.04 * le * h

    u_min, us = util_max(As_min_ext)
    if u_min <= TOL_UTIL:
        As_ext = As_min_ext
    else:
        u_max, _ = util_max(As_max_ext)
        if u_max > TOL_UTIL:
            As_ext = As_max_ext
            r.mensagens.append(Mensagem(
                "erro", "flexao",
                Texto(
                    f"Seção insuficiente à flexão: mesmo com 4% na zona de extremidade a utilização é {u_max:.2f}. Aumente a espessura, o comprimento ou o fck.",
                    f"Section inadequate in flexure: even with 4% in the boundary zone the utilization is {u_max:.2f}. Increase thickness, length or fck.",
                ),
            ))
        else:
            lo, hi = As_min_ext, As_max_ext
            for _ in range(12):
                mid = 0.5 * (lo + hi)
                if util_max(mid)[0] > TOL_UTIL:
                    lo = mid
                else:
                    hi = mid
            As_ext = hi
    u_fin, us = util_max(As_ext)
    for c, u in zip(calc, us):
        c.utilizacao = u
    gov_f = max(calc, key=lambda c: c.utilizacao)

    # Barras reais e utilização final com elas
    n_b, As_real = arm.barras_zona(As_ext * 1e4, op.phi_extremidade)
    r.As_extremidade = As_ext * 1e4
    r.barras_extremidade = f"{n_b} φ{op.phi_extremidade:g} ({n(As_real).replace('{,}', ',')} cm²)"
    s_a, As_a_real = arm.espacamento(As_alma_face * 1e4, op.phi_alma, 20.0)
    r.As_alma_face = As_alma_face * 1e4
    r.barras_alma = f"φ{op.phi_alma:g} c/ {s_a:g} cm".replace(".", ",")
    phi_t = arm.bitola_estribo(op.phi_extremidade)
    s_t = min(20.0, g.h, 12 * op.phi_extremidade / 10)
    r.estribos_extremidade = f"φ{phi_t:g} c/ {math.floor(s_t):g} cm"
    r.util_flexao = gov_f.utilizacao
    r.comb_flexao = f"{gov_f.comb.nome}: {gov_f.comb.expressao}"

    mem.add(
        "Armadura das zonas de extremidade (busca na superfície N–Mx–My)",
        "Boundary zone steel (search on the N–Mx–My surface)",
        r"\max_{comb}\ \eta(N_d, M_{xd}, M_{yd};\ A_{s,ext}) \le 1",
        rf"N_d = {n(gov_f.Nd, 1)}\ kN,\ M_{{xd}} = {n(gov_f.Mxd, 1)}\ kN \cdot m,\ M_{{yd}} = {n(gov_f.Myd, 1)}\ kN \cdot m",
        rf"A_{{s,ext}} = {n(As_ext * 1e4)}\ cm^2 \ (\eta = {n(gov_f.utilizacao, 3)})",
        "NBR 6118, 17.2",
    )
    mem.add(
        "Armadura longitudinal mínima",
        "Minimum longitudinal steel",
        r"A_{s,min} = 0{,}15\,\frac{N_d}{f_{yd}} \ge 0{,}004\,A_c",
        rf"A_{{s,min}} = \max\left(0{{,}}15 \cdot \frac{{{n(Nmax, 1)}}}{{{n(fyd / 10, 2)}}};\ 0{{,}}004 \cdot {n(Ac * 1e4, 0)}\right)",
        rf"A_{{s,min}} = {n(As_min_total * 1e4)}\ cm^2",
        "NBR 6118, 17.3.5.3.1",
    )

    # 3. Cortante no plano
    d = 0.8 * lw
    bw = h
    av2 = 1 - mat.fck / 250
    VRd2 = 0.27 * av2 * fcd * bw * d * 1e3
    fctm = _fctm(mat.fck)
    fctd = 0.7 * fctm / 1.4
    Vc0 = 0.6 * fctd * bw * d * 1e3
    rho_sw_min = 0.2 * fctm / mat.fyk

    def Vc(c: CombinacaoCalculo) -> float:
        M = abs(c.Myd if mp.M_no_plano == "My" else c.Mxd)
        if c.Nd > 0:
            M0 = c.Nd * lw / 6
            return 2 * Vc0 if M < 1e-9 else min(Vc0 * (1 + M0 / M), 2 * Vc0)
        if c.Nd < 0:
            e = M / abs(c.Nd)
            return 0.0 if e < lw / 2 - le / 2 else Vc0
        return Vc0

    def Asw_s(c: CombinacaoCalculo) -> float:
        return max(0.0, c.V_no_plano - Vc(c)) / (0.9 * d * fywd * 1e3)  # m²/m, duas faces

    gov_v = max(calc, key=lambda c: (Asw_s(c), c.V_no_plano))
    Asw = Asw_s(gov_v)
    Asw_min = rho_sw_min * bw
    As_h_face = max(Asw, Asw_min) / 2
    As_h_face = max(As_h_face, 0.25 * As_alma_face)
    r.As_horizontal_face = As_h_face * 1e4
    s_h, _ = arm.espacamento(As_h_face * 1e4, op.phi_alma, 20.0)
    r.barras_horizontal = f"φ{op.phi_alma:g} c/ {s_h:g} cm".replace(".", ",")
    r.util_cortante = gov_v.V_no_plano / VRd2
    r.comb_cortante = f"{gov_v.comb.nome}: {gov_v.comb.expressao}"

    mem.add(
        "Compressão diagonal do concreto (Modelo I, θ = 45°)",
        "Diagonal compression of concrete (Model I, θ = 45°)",
        r"V_{Rd2} = 0{,}27\,\alpha_{v2}\,f_{cd}\,b_w\,d \qquad \alpha_{v2} = 1 - \frac{f_{ck}}{250} \qquad d = 0{,}8\,\ell_w",
        rf"V_{{Rd2}} = 0{{,}}27 \cdot {n(av2, 3)} \cdot {n(fcd * 1e3, 0)} \cdot {n(bw, 2)} \cdot {n(d, 2)}",
        rf"V_{{Rd2}} = {n(VRd2, 1)}\ kN \ge V_{{Sd}} = {n(gov_v.V_no_plano, 1)}\ kN",
        "NBR 6118, 17.4.2.2",
    )
    mem.add(
        "Parcela do concreto e armadura horizontal (treliça de Mörsch)",
        "Concrete contribution and horizontal steel (Mörsch truss)",
        r"V_{c0} = 0{,}6\,f_{ctd}\,b_w\,d \qquad \frac{A_{sw}}{s} = \frac{V_{Sd} - V_c}{0{,}9\,d\,f_{ywd}}",
        rf"V_{{c0}} = 0{{,}}6 \cdot {n(fctd * 1e3, 0)} \cdot {n(bw, 2)} \cdot {n(d, 2)} = {n(Vc0, 1)}\ kN \qquad V_c = {n(Vc(gov_v), 1)}\ kN",
        rf"\frac{{A_{{sw}}}}{{s}} = {n(Asw * 1e4)}\ cm^2/m \ (\text{{mín. }} {n(Asw_min * 1e4)}\ cm^2/m)",
        "NBR 6118, 17.4.2.2 e 17.4.1.1.1",
    )
    if VRd2 < gov_v.V_no_plano:
        r.mensagens.append(Mensagem(
            "erro", "cortante",
            Texto(
                f"Cortante no plano acima de VRd2 = {VRd2:.0f} kN: as bielas de concreto esmagam. Aumente a espessura ou o fck.",
                f"In-plane shear exceeds VRd2 = {VRd2:.0f} kN: concrete struts crush. Increase thickness or fck.",
            ),
        ))

    # Parede baixa: verificação da biela principal
    if regime(parede).resultado == "D" and gov_v.V_no_plano > 0:
        z = lw - le
        theta = math.atan2(g.hw, z)
        C = gov_v.V_no_plano / math.cos(theta)
        w = le * math.sin(theta)
        sigma = C / (w * h) / 1e3
        fcd2 = 0.60 * av2 * fcd
        r.util_cortante = max(r.util_cortante, sigma / fcd2)
        mem.add(
            "Bielas e tirantes: biela diagonal principal",
            "Strut-and-tie: main diagonal strut",
            r"C = \frac{V_{Sd}}{\cos\theta} \qquad \sigma = \frac{C}{w\,h} \le f_{cd2} = 0{,}60\,\alpha_{v2}\,f_{cd}",
            rf"\theta = {n(math.degrees(theta), 1)}^\circ \qquad w = \ell_e \sin\theta = {n(w, 3)}\ m",
            rf"\sigma = {n(sigma)}\ MPa \le f_{{cd2}} = {n(fcd2)}\ MPa",
            "NBR 6118, 22.1 e 22.3",
        )
        if sigma > fcd2:
            r.mensagens.append(Mensagem(
                "erro", "biela",
                Texto(
                    "A biela diagonal da parede baixa excede fcd2. Aumente a espessura, a zona de extremidade ou o fck.",
                    "The squat wall diagonal strut exceeds fcd2. Increase thickness, boundary zone or fck.",
                ),
            ))

    # 4. Cortante fora do plano (laje sem armadura transversal)
    d_out = h - c_m - phi_t / 1000 - op.phi_extremidade / 2000
    As_tot = 2 * As_ext + As_alma_total
    rho1 = min(0.02, (As_tot / 2) / (lw * d_out))
    k = max(1.0, 1.6 - d_out)
    tau_rd = 0.25 * fctd
    gov_o = max(calc, key=lambda c: c.V_fora_plano)
    sigma_cp = max(gov_o.Nd, 0.0) / Ac / 1e3
    VRd1 = (tau_rd * k * (1.2 + 40 * rho1) + 0.15 * sigma_cp) * lw * d_out * 1e3
    mem.add(
        "Cortante fora do plano, sem armadura transversal",
        "Out-of-plane shear, without transverse reinforcement",
        r"V_{Rd1} = \left[\tau_{Rd}\,k\,(1{,}2 + 40\,\rho_1) + 0{,}15\,\sigma_{cp}\right] b_w\,d",
        rf"\tau_{{Rd}} = {n(tau_rd, 3)}\ MPa,\ k = {n(k, 2)},\ \rho_1 = {n(rho1, 4)},\ \sigma_{{cp}} = {n(sigma_cp, 2)}\ MPa",
        rf"V_{{Rd1}} = {n(VRd1, 1)}\ kN\ \ (V_{{Sd}} = {n(gov_o.V_fora_plano, 1)}\ kN)",
        "NBR 6118, 19.4.1",
    )
    if gov_o.V_fora_plano > VRd1:
        Vc0_out = 0.6 * fctd * lw * d_out * 1e3
        Asw_out = max(0.0, gov_o.V_fora_plano - Vc0_out) / (0.9 * d_out * fywd * 1e3)
        r.grampos_fora_plano = max(Asw_out / lw, rho_sw_min * h) * 1e4
        r.mensagens.append(Mensagem(
            "aviso", "cortante_fora",
            Texto(
                f"Cortante fora do plano acima de VRd1: prever grampos de {r.grampos_fora_plano:.2f} cm²/m por metro de parede.",
                f"Out-of-plane shear exceeds VRd1: provide cross-ties of {r.grampos_fora_plano:.2f} cm²/m per metre of wall.",
            ),
        ))
    r.util_cortante = max(r.util_cortante, gov_o.V_fora_plano / VRd1 if VRd1 > 0 else 0.0)

    # Taxa máxima
    if (2 * As_real / 1e4 + As_alma_total) > 0.04 * Ac:
        r.mensagens.append(Mensagem(
            "erro", "taxa_max",
            Texto("Armadura longitudinal acima de 4% de Ac (17.3.5.2.4).", "Longitudinal steel above 4% of Ac (17.3.5.2.4)."),
        ))

    r.governa = (
        Texto("Flexão", "Flexure") if r.util_flexao >= r.util_cortante else Texto("Cortante", "Shear")
    )
    if As_ext <= As_min_ext * 1.0001:
        r.governa = Texto("Armadura mínima", "Minimum steel")
    return r
