"""Máquina `Estagio` completa: quem escreve cada transição (docs/architecture/fluxo-agente.md)."""
from base import Diagrama, gerar
from xml.sax.saxutils import escape

ESTAGIOS = ["NOVO", "QUALIFICANDO", "QUALIFICADO", "AGENDADO", "INATIVO", "FRIO", "HANDOFF"]

# (origem, destino): (nó que escreve, tom)
T = {
    ("NOVO", "QUALIFICANDO"): ("qualificador", "azul"),
    ("NOVO", "QUALIFICADO"): ("consultor", "azul"),
    ("NOVO", "INATIVO"): ("followup", "ambar"),
    ("NOVO", "HANDOFF"): ("handoff · fallback · orçamento", "verde"),
    ("QUALIFICANDO", "QUALIFICADO"): ("consultor", "azul"),
    ("QUALIFICANDO", "AGENDADO"): ("agendador", "azul"),
    ("QUALIFICANDO", "INATIVO"): ("followup", "ambar"),
    ("QUALIFICANDO", "HANDOFF"): ("handoff · fallback · orçamento", "verde"),
    ("QUALIFICADO", "AGENDADO"): ("agendador", "azul"),
    ("QUALIFICADO", "INATIVO"): ("followup", "ambar"),
    ("QUALIFICADO", "HANDOFF"): ("handoff · fallback · orçamento", "verde"),
    ("AGENDADO", "QUALIFICANDO"): ("nova oportunidade", "cinza"),
    ("AGENDADO", "HANDOFF"): ("handoff (pedido do cliente)", "verde"),
    ("INATIVO", "QUALIFICANDO"): ("—", None),
    ("INATIVO", "AGENDADO"): ("agendador", "azul"),
    ("INATIVO", "INATIVO"): ("followup (nova tentativa)", "ambar"),
    ("INATIVO", "FRIO"): ("followup (esgotou)", "ambar"),
    ("INATIVO", "HANDOFF"): ("handoff", "verde"),
    ("FRIO", "QUALIFICANDO"): ("nova oportunidade", "cinza"),
    ("HANDOFF", "QUALIFICANDO"): ("nova oportunidade", "cinza"),
}


def montar() -> Diagrama:
    d = Diagrama(
        nome="estados-codigo", titulo="Transições de Estagio, uma a uma",
        subtitulo="Quem escreve cada mudança — linha é de onde sai, coluna é para onde vai",
        largura=1760, altura=960, rodape_dir="MORA · MÁQUINA DE ESTADOS",
        alt=("Matriz das transições de estágio do lead, com o nó do grafo responsável por cada "
             "mudança."))

    x0, rot, cw, y0, rh = 56, 232, 196, 214, 78
    # cabeçalho de colunas
    d.add(f'<text x="{x0 + 12}" y="{y0 - 22}" class="t-grp">DE ↓  ·  PARA →</text>')
    for j, e in enumerate(ESTAGIOS):
        cx = x0 + rot + j * cw
        d.add(f'<rect x="{cx + 4}" y="{y0 - 52}" width="{cw - 8}" height="40" rx="8" '
              f'fill="var(--grupo)"/>')
        d.add(f'<text x="{cx + cw / 2}" y="{y0 - 32}" class="t-sub" text-anchor="middle" '
              f'style="font-weight:700;font-size:11.5px">{escape(e)}</text>')

    for i, origem in enumerate(ESTAGIOS):
        y = y0 + i * rh
        d.add(f'<rect x="{x0}" y="{y + 4}" width="{rot - 8}" height="{rh - 8}" rx="8" '
              f'fill="var(--grupo)"/>')
        d.add(f'<text x="{x0 + 18}" y="{y + rh / 2}" class="t-sub" '
              f'style="font-weight:700;font-size:12.5px">{escape(origem)}</text>')
        for j, destino in enumerate(ESTAGIOS):
            cx = x0 + rot + j * cw
            par = T.get((origem, destino))
            if par is None:
                d.add(f'<circle cx="{cx + cw / 2}" cy="{y + rh / 2}" r="2" fill="var(--regua)"/>')
                continue
            texto, tom = par
            if tom is None:      # transição que muita gente supõe existir e não existe
                d.add(f'<rect x="{cx + 6}" y="{y + 10}" width="{cw - 12}" height="{rh - 20}" rx="8" '
                      f'fill="none" stroke="var(--vermelho)" stroke-width="1.1" stroke-dasharray="5 4"/>')
                d.add(f'<text x="{cx + cw / 2}" y="{y + rh / 2 - 8}" class="t-mini x-vermelho" '
                      f'text-anchor="middle" style="font-weight:700">não existe</text>')
                d.add(f'<text x="{cx + cw / 2}" y="{y + rh / 2 + 8}" class="t-mini" '
                      f'text-anchor="middle">o retorno é turno novo</text>')
                continue
            d.add(f'<rect x="{cx + 6}" y="{y + 10}" width="{cw - 12}" height="{rh - 20}" rx="8" '
                  f'fill="var(--{tom}-suave)"/>')
            palavras = texto.split(" · ") if " · " in texto else [texto]
            if len(palavras) == 1 and len(texto) > 16:
                corte = texto.rfind(" (")
                palavras = [texto[:corte], texto[corte + 1:]] if corte > 0 else [texto]
            for k, l in enumerate(palavras[:3]):
                dy = (rh / 2) - (len(palavras[:3]) - 1) * 7 + k * 14
                d.add(f'<text x="{cx + cw / 2}" y="{y + dy}" class="t-mini x-{tom}" '
                      f'text-anchor="middle" style="font-weight:600">{escape(l)}</text>')

    d.nota(880, 790, 1660, [
        "HANDOFF sai do fluxo automatizado: o agente silencia, registra a mensagem e notifica o corretor — a linha HANDOFF só tem saída por nova oportunidade.",
        "“Nova oportunidade” não é uma volta: nova_oportunidade_se_mudou_intencao cria um lead sucessor em QUALIFICANDO e encerra o anterior; vale nos",
        "estágios AGENDADO, HANDOFF, INATIVO e FRIO. O resumidor não muda estágio nenhum, e nenhum nó volta de INATIVO ou FRIO para QUALIFICANDO sozinho."])

    d.legenda([("azul", "Avanço do atendimento"), ("ambar", "Silêncio do cliente"),
               ("verde", "Passagem ao humano"), ("cinza", "Lead sucessor")], y=910)
    d.rodape("Mora · transições de estágio")
    return d


if __name__ == "__main__":
    print("\n".join(gerar(montar())))
