"""Integração da seção retangular por fibras e superfície de interação N–Mx–My.

A seção fica centrada na origem, com X horizontal e Y vertical (metros).
Convenções de sinal (compressão positiva):

    N  = Σ σ·dA
    Mx = −Σ σ·y·dA   (Mx positivo comprime a face inferior, y < 0)
    My = +Σ σ·x·dA   (My positivo comprime a face direita, x > 0)

Os estados últimos de deformação percorrem os domínios 1 a 5 por um único
parâmetro s ∈ [0, 3], para cada ângulo θ da direção mais comprimida:

    s ∈ [0, 1]  pivô A: armadura mais tracionada em −εsu (domínios 1 e 2)
    s ∈ [1, 2]  pivô B: borda mais comprimida em εcu (domínios 3, 4 e 4a)
    s ∈ [2, 3]  pivô C: deformação εc2 a (εcu − εc2)/εcu·H da borda (domínio 5)

N cresce com s, de tração pura (s = 0) a compressão uniforme (s = 3).
"""

from dataclasses import dataclass

import numpy as np

from .materiais import Aco, ConcretoACI, ConcretoNBR

EPS_SU = 10.0e-3  # alongamento último do aço usado para gerar os estados


@dataclass(frozen=True)
class Barra:
    x: float  # m
    y: float  # m
    area: float  # m²


@dataclass(frozen=True)
class Ponto:
    """Esforços resistentes de cálculo de um estado último (kN, kN·m)."""

    N: float
    Mx: float
    My: float
    phi: float = 1.0
    eps_t: float = 0.0  # deformação da barra mais tracionada (tração negativa)


class Secao:
    def __init__(
        self,
        bx: float,
        by: float,
        barras: list[Barra],
        concreto: ConcretoNBR | ConcretoACI,
        aco: Aco,
        tamanho_fibra: float = 0.01,
        max_fibras_lado: int = 200,
    ):
        self.bx, self.by = bx, by
        self.concreto, self.aco = concreto, aco
        self.aci = isinstance(concreto, ConcretoACI)

        nx = int(np.clip(np.ceil(bx / tamanho_fibra), 8, max_fibras_lado))
        ny = int(np.clip(np.ceil(by / tamanho_fibra), 8, max_fibras_lado))
        xs = (np.arange(nx) + 0.5) * bx / nx - bx / 2
        ys = (np.arange(ny) + 0.5) * by / ny - by / 2
        X, Y = np.meshgrid(xs, ys)
        self.xc, self.yc = X.ravel(), Y.ravel()
        self.Ac = np.full(self.xc.size, bx * by / (nx * ny))

        self.barras = list(barras)
        self.xs = np.array([b.x for b in barras], dtype=float)
        self.ys = np.array([b.y for b in barras], dtype=float)
        self.As = np.array([b.area for b in barras], dtype=float)

    # Estados de deformação (vetorizados: vários ângulos e parâmetros de uma vez)

    def _pontos(self, theta: np.ndarray, s_par: np.ndarray) -> dict[str, np.ndarray]:
        """Esforços resistentes de cálculo para pares (θ, s); arrays de mesmo tamanho."""
        theta = np.atleast_1d(np.asarray(theta, dtype=float))
        sp = np.atleast_1d(np.asarray(s_par, dtype=float))
        cu, c2 = self.concreto.eps_cu, self.concreto.eps_c2
        cth, sth = np.cos(theta), np.sin(theta)
        v_max = np.abs(cth) * self.bx / 2 + np.abs(sth) * self.by / 2
        v_min = -v_max
        H = v_max - v_min
        vs = np.outer(cth, self.xs) + np.outer(sth, self.ys)
        v_ref = vs.min(axis=1) if self.xs.size else v_min

        # deformações nas bordas comprimida (topo) e oposta (base)
        def na_base(v1, e1, v2, e2):
            return e1 + (e2 - e1) * (v_min - v1) / (v2 - v1)

        s1, s2 = sp <= 1.0, (sp > 1.0) & (sp <= 2.0)
        e_top = np.where(s1, -EPS_SU + np.clip(sp, 0, 1) * (cu + EPS_SU), cu)
        e_bot = na_base(v_ref, -EPS_SU, v_max, e_top)
        e1 = na_base(v_ref, -EPS_SU, v_max, cu)
        e_bot = np.where(s2, e1 * (2.0 - sp), e_bot)
        s3 = sp > 2.0
        u = (sp - 2.0) * c2
        v_c = v_max - (cu - c2) / cu * H
        top3 = c2 + (c2 - u) * (v_max - v_c) / (v_c - v_min)
        e_top = np.where(s3, top3, e_top)
        e_bot = np.where(s3, u, e_bot)

        grad = (e_top - e_bot) / H

        def eps(v):
            return e_bot[:, None] + grad[:, None] * (v - v_min[:, None])

        vc = np.outer(cth, self.xc) + np.outer(sth, self.yc)
        eps_s = eps(vs)
        if self.aci:
            with np.errstate(divide="ignore", invalid="ignore"):
                c_ln = np.where(e_bot >= 0, np.inf, e_top / (e_top - e_bot) * H)
            a = np.where(e_top > 0, self.concreto.beta1 * c_ln, 0.0)
            lim = (v_max - a)[:, None]
            sig_c = np.where(vc >= lim, 0.85 * self.concreto.fc, 0.0)
            sig_cb = np.where(vs >= lim, 0.85 * self.concreto.fc, 0.0)
            sig_c[e_top <= 0] = 0.0
            sig_cb[e_top <= 0] = 0.0
        else:
            sig_c = self.concreto.tensao(eps(vc))
            sig_cb = self.concreto.tensao(eps_s)
        sig_s = self.aco.tensao(eps_s) - sig_cb  # desconta o concreto deslocado

        N = (sig_c @ self.Ac + sig_s @ self.As) * 1e3
        Mx = -(sig_c @ (self.Ac * self.yc) + sig_s @ (self.As * self.ys)) * 1e3
        My = (sig_c @ (self.Ac * self.xc) + sig_s @ (self.As * self.xs)) * 1e3
        eps_t = e_bot + grad * (v_ref - v_min)
        phi = self._phi_vec(eps_t) if self.aci else np.ones_like(N)
        return {"N": phi * N, "Mx": phi * Mx, "My": phi * My, "phi": phi, "eps_t": eps_t}

    def ponto(self, theta: float, s_par: float) -> Ponto:
        p = self._pontos(np.array([theta]), np.array([s_par]))
        return Ponto(*(float(p[k][0]) for k in ("N", "Mx", "My", "phi", "eps_t")))

    # ACI: fator φ e teto de compressão

    def _phi_vec(self, eps_t: np.ndarray) -> np.ndarray:
        et, ey = -eps_t, self.aco.eps_y
        return np.clip(0.65 + 0.25 * (et - ey) / 0.003, 0.65, 0.90)

    def phi_aci(self, eps_t: float) -> float:
        """φ pela Tabela 21.2.2 (estribos comuns): 0,65 a 0,90."""
        return float(self._phi_vec(np.array([eps_t]))[0])

    def phiPn_max(self) -> float:
        """φPn,máx = 0,80·φ·[0,85·f'c·(Ag − Ast) + fy·Ast] (22.4.2), em kN."""
        Ag, Ast = self.bx * self.by, self.As.sum()
        P0 = 0.85 * self.concreto.fc * (Ag - Ast) + self.aco.fy * Ast
        return 0.80 * 0.65 * P0 * 1e3

    # Limites de N e contorno de momentos

    def N_min(self) -> float:
        return self.ponto(0.0, 0.0).N

    def N_max(self) -> float:
        n = self.ponto(0.0, 3.0).N
        return min(n, self.phiPn_max()) if self.aci else n

    def superficie(self, n_angulos: int = 72, n_s: int = 241) -> dict[str, np.ndarray]:
        """Superfície resistente amostrada em uma grade (θ, s), guardada para reuso."""
        chave = (n_angulos, n_s)
        cache = self.__dict__.setdefault("_sup", {})
        if chave not in cache:
            th = np.linspace(0.0, 2 * np.pi, n_angulos, endpoint=False)
            sg = np.linspace(0.0, 3.0, n_s)
            T, S = np.meshgrid(th, sg, indexing="ij")
            partes = {k: [] for k in ("N", "Mx", "My")}
            passo = max(1, 2_000_000 // max(1, self.xc.size * n_s))  # limita a memória
            for i in range(0, n_angulos, passo):
                p = self._pontos(T[i:i + passo].ravel(), S[i:i + passo].ravel())
                for k in partes:
                    partes[k].append(p[k].reshape(-1, n_s))
            sup = {k: np.vstack(v) for k, v in partes.items()}
            sup["N"] = np.maximum.accumulate(sup["N"], axis=1)  # N cresce com s
            cache[chave] = sup
        return cache[chave]

    def contorno(self, Nd: float, n_angulos: int = 72, n_s: int = 241) -> np.ndarray:
        """Curva (Mx, My) resistente para N = Nd; vazia se Nd estiver fora dos limites.

        Interpola linearmente em s, para cada θ, a superfície amostrada.
        """
        sup = self.superficie(n_angulos, n_s)
        pts = []
        for Nr, Mxr, Myr in zip(sup["N"], sup["Mx"], sup["My"]):
            if Nr[0] <= Nd <= Nr[-1]:
                pts.append((np.interp(Nd, Nr, Mxr), np.interp(Nd, Nr, Myr)))
        return np.array(pts) if pts else np.empty((0, 2))

    def utilizacao(self, Nd: float, Mxd: float, Myd: float, n_angulos: int = 72, n_s: int = 241) -> float:
        """Razão solicitante/resistente (≤ 1 atende).

        Com N fora dos limites resistentes, devolve a razão de N. Caso contrário,
        devolve |Md|/|MR| ao longo da direção do momento solicitante, no nível Nd.
        """
        n_max, n_min = self.N_max(), self.N_min()
        if Nd > n_max:
            return Nd / n_max
        if Nd < n_min:
            return Nd / n_min
        Md = np.hypot(Mxd, Myd)
        if Md < 1e-9:
            return max(Nd / n_max if Nd > 0 else 0.0, Nd / n_min if Nd < 0 else 0.0)
        poly = self.contorno(Nd, n_angulos, n_s)
        if len(poly) < 3:
            return np.inf
        MR = _raio_poligono(poly, np.array([Mxd, Myd]) / Md)
        return Md / MR if MR > 0 else np.inf

    def diagrama(self, eixo: str, n: int = 60) -> dict[str, np.ndarray]:
        """Pontos (N, M) do diagrama N–Mx ou N–My, para momento positivo e negativo."""
        th_pos, th_neg = (1.5 * np.pi, 0.5 * np.pi) if eixo == "x" else (0.0, np.pi)
        saida = {}
        for nome, th in (("positivo", th_pos), ("negativo", th_neg)):
            p = self._pontos(np.full(n, th), np.linspace(0, 3, n))
            N, M = p["N"], p["Mx"] if eixo == "x" else p["My"]
            if self.aci:
                N = np.minimum(N, self.phiPn_max())
            saida[nome] = np.column_stack([N, M])
        return saida


def _raio_poligono(poly: np.ndarray, d: np.ndarray) -> float:
    """Distância da origem até o contorno do polígono ao longo da direção unitária d."""
    melhor = 0.0
    P, Q = poly, np.roll(poly, -1, axis=0)
    for p, q in zip(P, Q):
        e = q - p
        den = d[0] * (-e[1]) - d[1] * (-e[0])
        if abs(den) < 1e-15:
            continue
        # resolve t·d = p + u·e
        t = (p[0] * (-e[1]) - p[1] * (-e[0])) / den
        u = (d[0] * p[1] - d[1] * p[0]) / den
        if t > 0 and -1e-9 <= u <= 1 + 1e-9:
            melhor = max(melhor, t)
    return melhor
