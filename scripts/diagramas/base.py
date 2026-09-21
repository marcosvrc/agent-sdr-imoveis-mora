"""Sistema visual dos diagramas do Mora.

Um diagrama é escrito como código (ver os módulos `d01_*.py` … `d10_*.py`) e sai como um SVG. O
SVG é texto: entra no diff, renderiza no GitHub e no portal sem plugin, e não depende de ferramenta
externa para ser regerado — `make diagramas` refaz todos.

Por que não Mermaid: o Mermaid resolve o layout sozinho, e é justamente isso que impede o
controle de leitura que estes diagramas precisam (agrupamento, hierarquia tipográfica, cor com
significado). Aqui a posição é declarada; em troca, um teste confere que nenhum texto transborda
da caixa que o contém (`verificar.py`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from xml.sax.saxutils import escape

# --------------------------------------------------------------------------- paleta

PALETA = {
    "fundo": "#F4F7FA", "cabecalho": "#0E2433", "cabecalho-txt": "#FFFFFF",
    "cabecalho-sub": "#9DB3C4", "acento": "#3FC7B4",
    "tinta": "#12293C", "tinta2": "#5B7387", "tinta3": "#8497A8",
    "cartao": "#FFFFFF", "cartao-linha": "#DCE4EC", "sombra": "#0E243310",
    "grupo": "#E9F1F8", "grupo-linha": "#D5E2EE", "grupo-rotulo": "#2C5F84",
    "azul": "#2E76B8", "azul-suave": "#E4EFF9",
    "verde": "#0E7F72", "verde-suave": "#DDF0EC",
    "roxo": "#7A4CC0", "roxo-suave": "#EDE6F9",
    "cinza": "#64798C", "cinza-suave": "#E8EDF2",
    "ambar": "#A9701A", "ambar-suave": "#FBF1DF", "ambar-linha": "#E8D5AE",
    "vermelho": "#B04437", "vermelho-suave": "#FAE6E3",
    "regua": "#DCE4EC",
}

FONTE = "Inter,'Segoe UI',system-ui,-apple-system,'Helvetica Neue',Arial,sans-serif"

# Largura média por caractere, em fração do tamanho da fonte. Serve para centralizar pílulas e
# estimar transbordo na hora de escrever o diagrama; a conferência de verdade é no navegador.
_LARG = {600: 0.575, 500: 0.545, 400: 0.535}


def largura_texto(texto: str, tamanho: float, peso: int = 400) -> float:
    return len(texto) * tamanho * _LARG.get(peso, 0.535)


# --------------------------------------------------------------------------- ícones (24×24, traço)

ICONES = {
    "janela": "M3 5.5h18v13H3zM3 9.5h18M6 7.5h.01M8.5 7.5h.01",
    "aviao": "M21.5 3.5 2.5 10.2l6.6 2.3 2.3 6.6z M9.1 12.5 21.5 3.5",
    "codigo": "M8.5 8 4.5 12l4 4M15.5 8l4 4-4 4",
    "camadas": "M12 3.5 3 8l9 4.5L21 8zM3 12.5 12 17l9-4.5M3 16.5 12 21l9-4.5",
    "faisca": "M12 3.2 13.9 9 19.8 10.9 13.9 12.8 12 18.6 10.1 12.8 4.2 10.9 10.1 9z",
    "relogio": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7.2V12l3.2 2",
    "banco": "M12 3.5c4.4 0 8 1.2 8 2.7S16.4 9 12 9 4 7.7 4 6.2 7.6 3.5 12 3.5zM4 6.2v11.6c0 1.5 3.6 2.7 8 2.7s8-1.2 8-2.7V6.2M4 12c0 1.5 3.6 2.7 8 2.7s8-1.2 8-2.7",
    "imagem": "M3.5 4.5h17v15h-17zM3.5 15l4.5-4 4 3.5 3.5-3 5 4.5M8.2 9.4h.01",
    "raio": "M13.2 2.5 4.5 13.6h6l-.7 7.9 8.7-11.1h-6z",
    "tomada": "M14.5 4.5 19.5 9.5M9.5 14.5 4.5 19.5M10.5 6.5l7 7-2.6 2.6a4.95 4.95 0 0 1-7-7zM13.5 17.5l-7-7",
    "predio": "M4.5 20.5V5.2l8-2.7v18M12.5 20.5h7V9.5h-7M7.5 8.5h2M7.5 12h2M7.5 15.5h2M15 12.5h1.5M15 16h1.5M2.5 20.5h19",
    "pessoa": "M12 12.2a4.1 4.1 0 1 0 0-8.2 4.1 4.1 0 0 0 0 8.2zM4.5 20.5c0-3.7 3.4-6.3 7.5-6.3s7.5 2.6 7.5 6.3",
    "agenda": "M4.5 5.5h15v15h-15zM4.5 10h15M8.5 3v4.5M15.5 3v4.5M9 15l2.2 2.2L15.5 13",
    "lista": "M6.5 3.5h11v17h-11zM9.5 8.5h5M9.5 12h5M9.5 15.5h3",
    "certo": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM8.2 12.2l2.6 2.6 5-5.2",
    "balao": "M20.5 12.5c0 4-3.8 7.2-8.5 7.2-1.2 0-2.3-.2-3.3-.5l-5.2 1.6 1.7-4.3a6.8 6.8 0 0 1-1.7-4.4c0-4 3.8-7.2 8.5-7.2s8.5 3.2 8.5 7.2z",
    "gelo": "M12 2.8v18.4M4 7.4l16 9.2M20 7.4 4 16.6M12 6.5 9.5 4.6M12 6.5l2.5-1.9M12 17.5l-2.5 1.9M12 17.5l2.5 1.9",
    "lupa": "M11 18.2a7.2 7.2 0 1 0 0-14.4 7.2 7.2 0 0 0 0 14.4zM16.4 16.4 20.5 20.5",
    "escudo": "M12 2.8 4.5 6v6c0 4.6 3.2 7.8 7.5 9.2 4.3-1.4 7.5-4.6 7.5-9.2V6z",
    "ramo": "M6.5 7.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM6.5 21.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM17.5 9.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM6.5 7.5v9M6.5 13.5h6a5 5 0 0 0 5-4",
    "engrenagem": "M12 15.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4zM19.4 14.6a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1v.2a2 2 0 0 1-4 0v-.1a1.6 1.6 0 0 0-2.8-1.1l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0-1.1-2.7h-.2a2 2 0 0 1 0-4h.1a1.6 1.6 0 0 0 1.1-2.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3h.1A1.6 1.6 0 0 0 10 3.1v-.2a2 2 0 0 1 4 0v.1a1.6 1.6 0 0 0 2.7 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0 1.1 2.7h.2a2 2 0 0 1 0 4h-.1a1.6 1.6 0 0 0-1.3 1z",
    "caixas": "M3.5 3.5h7v7h-7zM13.5 3.5h7v7h-7zM3.5 13.5h7v7h-7zM13.5 13.5h7v7h-7z",
    "fila": "M3.5 6.5h17M3.5 12h17M3.5 17.5h11",
    "alvo": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 16.5a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9zM12 13.8a1.8 1.8 0 1 0 0-3.6 1.8 1.8 0 0 0 0 3.6z",
    "seta": "M4.5 12h15M13.5 6l6 6-6 6",
    "mao": "M8.5 11V5.2a1.7 1.7 0 0 1 3.4 0V11M11.9 11V4.2a1.7 1.7 0 0 1 3.4 0V11M15.3 11V6.2a1.7 1.7 0 0 1 3.4 0v8.3c0 3.7-2.6 6.5-6.4 6.5-3.1 0-4.6-1.3-6.2-3.6l-2-3a1.7 1.7 0 0 1 2.7-2l1.3 1.6",
    "nuvem": "M7.2 19.5a4.7 4.7 0 0 1-.4-9.4 6 6 0 0 1 11.5 1.6 4 4 0 0 1-.8 7.8z",
}


def _icone(nome: str, x: float, y: float, cor: str, tamanho: float = 22) -> str:
    d = ICONES[nome]
    e = tamanho / 24
    return (f'<g transform="translate({x:.1f},{y:.1f}) scale({e:.4f})" fill="none" stroke="{cor}" '
            f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
            f'<path d="{d}"/></g>')


# --------------------------------------------------------------------------- documento

@dataclass
class Diagrama:
    nome: str
    titulo: str
    subtitulo: str
    largura: int
    altura: int
    rodape_dir: str = "MORA · COMITÊ DE ARQUITETURA"
    _corpo: list[str] = field(default_factory=list)
    _defs: list[str] = field(default_factory=list)
    alt: str = ""
    ALTURA_CABECALHO = 92

    # ---------------------------------------------------------------- infra
    def add(self, s: str) -> None:
        self._corpo.append(s)

    def _seta_defs(self) -> str:
        marcas = []
        for tom in ("azul", "verde", "roxo", "cinza", "ambar", "vermelho", "tinta2"):
            marcas.append(
                f'<marker id="p-{tom}" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" '
                f'markerHeight="7" orient="auto-start-reverse">'
                f'<path d="M0.5 1.2 9 5 0.5 8.8 2.6 5z" class="f-{tom}"/></marker>')
        return "".join(marcas)

    def svg(self, tema: dict) -> str:
        c = tema
        estilo = f"""
  text{{font-family:{FONTE};dominant-baseline:middle}}
  .t-tit{{font-size:17px;font-weight:600;fill:{c['tinta']}}}
  .t-tit-s{{font-size:14.5px;font-weight:600;fill:{c['tinta']}}}
  .t-sub{{font-size:12px;font-weight:400;fill:{c['tinta2']}}}
  .t-sub-s{{font-size:11px;font-weight:400;fill:{c['tinta2']}}}
  .t-mini{{font-size:10.5px;font-weight:400;fill:{c['tinta3']}}}
  .t-grp{{font-size:12px;font-weight:700;fill:{c['grupo-rotulo']};letter-spacing:.07em}}
  .t-grp-s{{font-size:11px;font-weight:400;fill:{c['tinta3']}}}
  .t-seta{{font-size:11.5px;font-weight:500}}
  .t-leg{{font-size:11.5px;font-weight:500;fill:{c['tinta2']}}}
  .t-rod{{font-size:10px;font-weight:700;fill:{c['tinta3']};letter-spacing:.09em}}
  .t-cab{{font-size:27px;font-weight:700;fill:{c['cabecalho-txt']}}}
  .t-cab-s{{font-size:13.5px;font-weight:400;fill:{c['cabecalho-sub']}}}
  .t-cab-r{{font-size:10.5px;font-weight:700;fill:{c['cabecalho-sub']};letter-spacing:.09em}}
  .cartao{{fill:{c['cartao']};stroke:{c['cartao-linha']};stroke-width:1}}
  .grupo{{fill:{c['grupo']};stroke:{c['grupo-linha']};stroke-width:1}}
  .linha{{stroke:{c['regua']};stroke-width:1}}
  .s-azul{{stroke:{c['azul']}}} .f-azul{{fill:{c['azul']}}} .x-azul{{fill:{c['azul']}}}
  .s-verde{{stroke:{c['verde']}}} .f-verde{{fill:{c['verde']}}} .x-verde{{fill:{c['verde']}}}
  .s-roxo{{stroke:{c['roxo']}}} .f-roxo{{fill:{c['roxo']}}} .x-roxo{{fill:{c['roxo']}}}
  .s-cinza{{stroke:{c['cinza']}}} .f-cinza{{fill:{c['cinza']}}} .x-cinza{{fill:{c['cinza']}}}
  .s-ambar{{stroke:{c['ambar']}}} .f-ambar{{fill:{c['ambar']}}} .x-ambar{{fill:{c['ambar']}}}
  .s-vermelho{{stroke:{c['vermelho']}}} .f-vermelho{{fill:{c['vermelho']}}} .x-vermelho{{fill:{c['vermelho']}}}
  .s-tinta2{{stroke:{c['tinta2']}}} .f-tinta2{{fill:{c['tinta2']}}} .x-tinta2{{fill:{c['tinta2']}}}
  .aresta{{fill:none;stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round}}
"""
        cab = self.ALTURA_CABECALHO
        partes = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.largura} {self.altura}" '
            f'width="{self.largura}" height="{self.altura}" role="img" '
            f'aria-label="{escape(self.alt or self.titulo)}">',
            f"<style>{estilo}</style>",
            f"<defs>{self._seta_defs()}{''.join(self._defs)}</defs>",
            f'<rect width="{self.largura}" height="{self.altura}" fill="{c["fundo"]}"/>',
            f'<rect width="{self.largura}" height="{cab}" fill="{c["cabecalho"]}"/>',
            f'<rect x="40" y="26" width="5" height="{cab - 52}" rx="2.5" fill="{c["acento"]}"/>',
            f'<text x="60" y="{cab / 2 - 11}" class="t-cab">{escape(self.titulo)}</text>',
            f'<text x="61" y="{cab / 2 + 15}" class="t-cab-s">{escape(self.subtitulo)}</text>',
            f'<text x="{self.largura - 40}" y="{cab / 2}" class="t-cab-r" text-anchor="end">'
            f'{escape(self.rodape_dir)}</text>',
            *self._corpo,
        ]
        partes.append("</svg>")
        return "\n".join(partes)

    # ---------------------------------------------------------------- primitivas
    def grupo(self, x, y, w, h, numero: str, rotulo: str, sub: str = "") -> None:
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" class="grupo"/>')
        self.add(f'<text x="{x + 20}" y="{y + 22}" class="t-grp">{escape(numero)} {escape(rotulo.upper())}</text>')
        if sub:
            self.add(f'<text x="{x + 20}" y="{y + 40}" class="t-grp-s">{escape(sub)}</text>')

    def painel(self, x, y, w, h, rotulo: str, sub: str = "", tom: str = "ambar") -> None:
        """Painel de destaque (fundo âmbar) — usado para o bloco de inatividade."""
        c = "ambar"
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" '
                 f'fill="var(--{c}-suave)" stroke="var(--{c}-linha)" stroke-width="1"/>')
        self.add(f'<text x="{x + 20}" y="{y + 22}" class="t-grp x-{c}">{escape(rotulo.upper())}</text>')
        if sub:
            self.add(f'<text x="{x + 20}" y="{y + 40}" class="t-grp-s">{escape(sub)}</text>')

    def cartao(self, x, y, w, h, titulo: str, linhas: list[str] | None = None,
               icone: str | None = None, tom: str = "azul", pequeno: bool = False,
               destaque: str | None = None) -> None:
        linhas = linhas or []
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="11" class="cartao"/>')
        if destaque:
            self.add(f'<rect x="{x}" y="{y}" width="4.5" height="{h}" rx="2.2" class="f-{destaque}"/>')
        tx = x + 18
        if icone:
            cy = y + (34 if linhas else h / 2)
            self.add(f'<rect x="{x + 16}" y="{cy - 17}" width="34" height="34" rx="9" '
                     f'fill="var(--{tom}-suave)"/>')
            self.add(_icone(icone, x + 22, cy - 11, f"var(--{tom})", 22))
            tx = x + 60
        cls_t = "t-tit-s" if pequeno else "t-tit"
        if linhas:
            ty = y + (26 if icone else 24)
            self.add(f'<text x="{tx}" y="{ty}" class="{cls_t}">{escape(titulo)}</text>')
            for i, l in enumerate(linhas):
                self.add(f'<text x="{tx}" y="{ty + 22 + i * 16}" class="t-sub">{escape(l)}</text>')
        else:
            self.add(f'<text x="{tx}" y="{y + h / 2}" class="{cls_t}">{escape(titulo)}</text>')

    def caixa(self, x, y, w, h, titulo: str, sub: str = "", tom: str | None = None) -> None:
        """Cartão compacto de rótulo centralizado, para cadeias curtas."""
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" class="cartao"/>')
        if tom:
            self.add(f'<rect x="{x}" y="{y}" width="4" height="{h}" rx="2" class="f-{tom}"/>')
        cy = y + (h / 2 - 9 if sub else h / 2)
        self.add(f'<text x="{x + w / 2}" y="{cy}" class="t-tit-s" text-anchor="middle">{escape(titulo)}</text>')
        if sub:
            self.add(f'<text x="{x + w / 2}" y="{cy + 19}" class="t-sub-s" text-anchor="middle">{escape(sub)}</text>')

    def pilula(self, cx, cy, texto: str, tom: str = "roxo", w: float | None = None) -> None:
        w = w or largura_texto(texto, 13, 600) + 34
        self.add(f'<rect x="{cx - w / 2}" y="{cy - 16}" width="{w}" height="32" rx="16" '
                 f'fill="var(--{tom}-suave)"/>')
        self.add(f'<text x="{cx}" y="{cy}" class="t-tit-s x-{tom}" text-anchor="middle">'
                 f'{escape(texto)}</text>')

    def aresta(self, pontos: list[tuple[float, float]], tom: str = "cinza", rotulo: str = "",
               tracejada: bool = False, rot_xy: tuple[float, float] | None = None,
               ancora: str = "middle", raio: float = 12, ponta: bool = True,
               rot_linhas: list[str] | None = None) -> None:
        d = _caminho(pontos, raio)
        tr = ' stroke-dasharray="6 5"' if tracejada else ""
        m = f' marker-end="url(#p-{tom})"' if ponta else ""
        self.add(f'<path d="{d}" class="aresta s-{tom}"{tr}{m}/>')
        linhas = rot_linhas or ([rotulo] if rotulo else [])
        if linhas:
            if rot_xy:
                lx, ly = rot_xy
            else:
                i = len(pontos) // 2
                (x1, y1), (x2, y2) = pontos[i - 1], pontos[i]
                lx, ly = (x1 + x2) / 2, (y1 + y2) / 2 - 12
            for j, l in enumerate(linhas):
                self.add(f'<text x="{lx}" y="{ly + j * 15}" class="t-seta x-{tom}" '
                         f'text-anchor="{ancora}">{escape(l)}</text>')

    def nota(self, x, y, w, linhas: list[str], ancora: str = "middle") -> float:
        h = 14 + len(linhas) * 16
        self.add(f'<rect x="{x - (w / 2 if ancora == "middle" else 0)}" y="{y}" width="{w}" '
                 f'height="{h}" rx="7" class="cartao"/>')
        tx = x if ancora == "middle" else x + 14
        for i, l in enumerate(linhas):
            self.add(f'<text x="{tx}" y="{y + 15 + i * 16}" class="t-sub-s" '
                     f'text-anchor="{ancora}">{escape(l)}</text>')
        return h

    def legenda(self, itens: list[tuple[str, str]], y: float | None = None,
                tracejados: set[int] | None = None) -> None:
        y = y if y is not None else self.altura - 46
        tracejados = tracejados or set()
        self.add(f'<line x1="40" y1="{y - 26}" x2="{self.largura - 40}" y2="{y - 26}" class="linha"/>')
        passo = (self.largura - 120) / max(len(itens), 1)
        for i, (tom, texto) in enumerate(itens):
            x = 42 + i * passo
            tr = ' stroke-dasharray="5 4"' if i in tracejados else ""
            self.add(f'<path d="M{x} {y}h34" class="aresta s-{tom}"{tr} marker-end="url(#p-{tom})"/>')
            self.add(f'<text x="{x + 46}" y="{y}" class="t-leg">{escape(texto)}</text>')

    # ---------------------------------------------------------------- sequência
    def sequencia(self, colunas: list[tuple[str, str, str]], y: float, larg: float = 196,
                  gap: float = 14, altura_cab: float = 88, ate: float | None = None) -> None:
        """Cabeçalhos das raias + linhas de vida. `colunas` = [(titulo, sub, icone)]."""
        self._seq_x = []
        total = len(colunas) * larg + (len(colunas) - 1) * gap
        x0 = (self.largura - total) / 2
        for i, (titulo, sub, icone) in enumerate(colunas):
            x = x0 + i * (larg + gap)
            self._seq_x.append(x + larg / 2)
            self.add(f'<rect x="{x}" y="{y}" width="{larg}" height="{altura_cab}" rx="10" class="cartao"/>')
            self.add(_icone(icone, x + 16, y + 15, "var(--azul)", 21))
            self.add(f'<text x="{x + 46}" y="{y + 26}" class="t-tit-s">{escape(titulo)}</text>')
            if sub:
                self.add(f'<text x="{x + 16}" y="{y + 60}" class="t-mini">{escape(sub)}</text>')
        fim = ate if ate is not None else self.altura - 110
        for cx in self._seq_x:
            self.add(f'<line x1="{cx}" y1="{y + altura_cab}" x2="{cx}" y2="{fim}" '
                     f'stroke="var(--cartao-linha)" stroke-width="1.2" stroke-dasharray="4 6"/>')

    def quadro(self, x, y, w, h, rotulo: str, tom: str = "cinza") -> None:
        """Moldura rotulada — o `loop`/`alt` dos diagramas de sequência."""
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="none" '
                 f'stroke="var(--{tom})" stroke-width="1.2" stroke-dasharray="7 5" opacity="0.7"/>')
        lw = largura_texto(rotulo, 11, 700) + 26
        self.add(f'<rect x="{x}" y="{y}" width="{lw}" height="26" rx="8" fill="var(--{tom}-suave)"/>')
        self.add(f'<text x="{x + 13}" y="{y + 13}" class="t-seta x-{tom}" '
                 f'style="font-weight:700">{escape(rotulo)}</text>')

    def faixa(self, y, h, rotulo: str, tom: str = "azul") -> None:
        self.add(f'<rect x="24" y="{y}" width="{self.largura - 48}" height="{h}" rx="12" '
                 f'fill="var(--{tom}-suave)" opacity="0.55"/>')
        self.add(f'<text x="48" y="{y + 20}" class="t-grp">{escape(rotulo.upper())}</text>')

    def ativacao(self, coluna: int, y0, y1, tom: str = "azul") -> None:
        cx = self._seq_x[coluna]
        self.add(f'<rect x="{cx - 6}" y="{y0}" width="12" height="{y1 - y0}" rx="5" '
                 f'fill="var(--{tom}-suave)" stroke="var(--{tom})" stroke-width="1"/>')

    def passo(self, de: int, para: int, y, linhas: list[str], numero: int | None = None,
              tom: str = "azul", tracejada: bool = False) -> None:
        """Mensagem entre raias, com nota acima e selo numerado na origem."""
        xa, xb = self._seq_x[de], self._seq_x[para]
        sentido = 1 if xb > xa else -1
        xi, xf = xa + sentido * 7, xb - sentido * 7
        if linhas:
            w = max(largura_texto(l, 12) for l in linhas) + 40
            cx = (xa + xb) / 2
            cx = min(max(cx, w / 2 + 30), self.largura - w / 2 - 30)
            self.nota(cx, y - 18 - len(linhas) * 16, w, linhas)
        tr = ' stroke-dasharray="7 5"' if tracejada else ""
        self.add(f'<path d="M{xi} {y}H{xf}" class="aresta s-{tom}"{tr} marker-end="url(#p-{tom})"/>')
        if numero is not None:
            self.add(f'<circle cx="{xi}" cy="{y}" r="11" class="f-{tom}"/>')
            self.add(f'<text x="{xi}" y="{y + 0.5}" text-anchor="middle" '
                     f'style="font-size:11px;font-weight:700;fill:#fff">{numero}</text>')

    def passo_proprio(self, coluna: int, y, linhas: list[str], numero: int | None = None,
                      tom: str = "azul") -> None:
        cx = self._seq_x[coluna]
        self.add(f'<path d="M{cx + 7} {y - 13}h26a5 5 0 0 1 5 5v16a5 5 0 0 1-5 5h-26" '
                 f'class="aresta s-{tom}" marker-end="url(#p-{tom})"/>')
        w = max(largura_texto(l, 12) for l in linhas) + 40
        self.nota(cx + 54 + w / 2, y - 22, w, linhas)
        if numero is not None:
            self.add(f'<circle cx="{cx + 7}" cy="{y + 13}" r="11" class="f-{tom}"/>')
            self.add(f'<text x="{cx + 7}" y="{y + 13.5}" text-anchor="middle" '
                     f'style="font-size:11px;font-weight:700;fill:#fff">{numero}</text>')

    # ---------------------------------------------------------------- estados
    def estado(self, x, y, w, h, nome: str, sub: str = "", icone: str = "balao",
               tom: str = "verde", final: bool = False) -> None:
        self.cartao(x, y, w, h, nome, [sub] if sub else None, icone, tom, destaque=tom)

    def marco(self, cx, cy, texto: str = "", inicio: bool = True) -> None:
        if inicio:
            self.add(f'<circle cx="{cx}" cy="{cy}" r="10" fill="var(--tinta)"/>')
        else:
            self.add(f'<circle cx="{cx}" cy="{cy}" r="11" fill="none" stroke="var(--tinta)" stroke-width="2"/>')
            self.add(f'<circle cx="{cx}" cy="{cy}" r="6" fill="var(--tinta)"/>')
        if texto:
            self.add(f'<text x="{cx + 22}" y="{cy}" class="t-tit-s">{escape(texto)}</text>')

    def rodape(self, esquerda: str = "") -> None:
        if esquerda:
            self.add(f'<text x="40" y="{self.altura - 20}" class="t-rod">{escape(esquerda.upper())}</text>')


def _caminho(pontos: list[tuple[float, float]], raio: float = 12) -> str:
    """Caminho ortogonal com cantos arredondados. Pontos intermediários viram cotovelos."""
    if len(pontos) < 2:
        raise ValueError("aresta precisa de ao menos dois pontos")
    d = [f"M{pontos[0][0]:.1f} {pontos[0][1]:.1f}"]
    for i in range(1, len(pontos) - 1):
        xa, ya = pontos[i - 1]
        xb, yb = pontos[i]
        xc, yc = pontos[i + 1]
        r = min(raio, abs(xb - xa) / 2 or raio, abs(yb - ya) / 2 or raio,
                abs(xc - xb) / 2 or raio, abs(yc - yb) / 2 or raio)
        ux, uy = _unit(xb - xa, yb - ya)
        vx, vy = _unit(xc - xb, yc - yb)
        d.append(f"L{xb - ux * r:.1f} {yb - uy * r:.1f}")
        d.append(f"Q{xb:.1f} {yb:.1f} {xb + vx * r:.1f} {yb + vy * r:.1f}")
    d.append(f"L{pontos[-1][0]:.1f} {pontos[-1][1]:.1f}")
    return " ".join(d)


def _unit(dx, dy):
    n = (dx ** 2 + dy ** 2) ** 0.5 or 1
    return dx / n, dy / n


def gerar(d: Diagrama, destino: str = "docs/assets/diagramas") -> list[str]:
    """Escreve <nome>.svg. Tema único: o desenho é claro nos dois temas do portal — foi uma
    escolha, para não manter dois arquivos por diagrama e duas chances de eles divergirem."""
    import pathlib
    svg = d.svg(PALETA)
    # as primitivas usam var(--x); resolvemos para valor literal, porque o SVG é consumido
    # via <img> (GitHub e portal) e não herda variáveis da página.
    for chave, valor in PALETA.items():
        svg = svg.replace(f"var(--{chave})", valor)
    p = pathlib.Path(destino) / f"{d.nome}.svg"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(svg, encoding="utf-8")
    return [str(p)]
