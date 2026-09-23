"""Indexa as fotos de data/fotos-acervo/ e escreve data/imoveis/fotos_pool.json.

Uso: python scripts/indexar_fotos.py [--largura 1200] [--qualidade 78]

O acervo de demonstração precisa de fotos que pareçam imóvel. Elas não nascem aqui: alguém baixa
de um banco de imagens com licença livre para `data/fotos-acervo/<categoria>/`, e este script
normaliza (redimensiona, converte para JPEG progressivo, renomeia em sequência) e publica a lista
que `scripts/gerar_imoveis.py` consome.

Duas decisões que valem explicação:

* **O prefixo servido é `/acervo/`, não `/fotos/`.** `/fotos/%` é reservado às fotos enviadas pelo
  painel, e o `upsert` do acervo usa exatamente esse prefixo para decidir precedência (ADR-0015):
  foto do painel vence o CRM, que vence o arquivo. Se as fotos do arquivo entrassem como `/fotos/`,
  passariam a se defender da reindexação como se um humano as tivesse enviado.
* **Renomeia em sequência determinística.** O nome que vem do banco de imagens carrega id do
  fotógrafo e do serviço; o acervo referencia `residencial-03.jpg`. A origem fica registrada em
  `data/fotos-acervo/PROCEDENCIA.md`, que este script cria vazio e não sobrescreve.
* **O original vai para `<categoria>/originais/` depois de convertido.** Sem isso, rodar o script
  duas vezes converteria o mesmo arquivo de novo e o acervo ganharia fotos duplicadas com nomes
  diferentes. A pasta `originais/` fica fora do git (ver .gitignore): é o arquivo pesado que já
  existe convertido ao lado.
"""
import argparse
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ORIGEM = RAIZ / "data/fotos-acervo"
DESTINO = RAIZ / "data/imoveis/fotos_pool.json"
CATEGORIAS = ("residencial", "sala-comercial", "loja", "galpao")
ENTRADAS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
PROCEDENCIA = ORIGEM / "PROCEDENCIA.md"
MODELO_PROCEDENCIA = """# Procedência das fotos do acervo

Fotos de demonstração, baixadas de bancos de imagem com licença de uso livre. Preencha uma linha
por arquivo — a licença é a razão de existir deste arquivo, e um acervo sem procedência é um
problema jurídico esperando a publicação.

| Arquivo | Origem (URL) | Autor | Licença |
|---|---|---|---|
"""


def normalizar(entrada: Path, saida: Path, largura: int, qualidade: int) -> None:
    try:
        from PIL import Image, ImageOps
    except ModuleNotFoundError:      # preparação de massa não é dependência de execução: o Pillow
        raise SystemExit(            # não está em nenhum pyproject, e é instalado só para isto.
            "✗ este script precisa do Pillow: pip install pillow") from None
    with Image.open(entrada) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        if im.width > largura:
            im = im.resize((largura, round(im.height * largura / im.width)), Image.LANCZOS)
        # `optimize` e `progressive` porque estas imagens são servidas na vitrine, e a primeira
        # tela do portal carrega doze cards de uma vez.
        im.save(saida, "JPEG", quality=qualidade, optimize=True, progressive=True)


def main(largura: int = 1200, qualidade: int = 78) -> None:
    pool: dict[str, object] = {
        "_sobre": ("Gerado por scripts/indexar_fotos.py a partir de data/fotos-acervo/. "
                   "Consumido por scripts/gerar_imoveis.py. Não editar à mão."),
        "_servido_por": "GET /acervo/{categoria}/{arquivo} (services/api), de SDR_FOTOS_ACERVO_DIR",
    }
    total = 0
    for categoria in CATEGORIAS:
        pasta = ORIGEM / categoria
        pasta.mkdir(parents=True, exist_ok=True)
        # Ordem alfabética do nome original: o resultado tem de ser o mesmo em qualquer máquina.
        entradas = sorted((p for p in pasta.iterdir()
                           if p.is_file() and p.suffix.lower() in ENTRADAS
                           and not p.name.startswith(categoria)),
                          key=lambda p: p.name.lower())
        guardados = pasta / "originais"
        for p in entradas:
            # `casa` ou `sobrado` no nome do ORIGINAL marca a foto como de imóvel de rua, e o
            # gerador só a usa como capa de casa e sobrado. Sem isso, um anúncio de apartamento
            # abriria com a fachada de uma casa — incoerência que o cliente vê antes do título.
            marca = "-casa" if any(k in p.stem.lower() for k in ("casa", "sobrado")) else ""
            proximo = len(sorted(pasta.glob(f"{categoria}{marca}-[0-9][0-9].jpg"))) + 1
            saida = pasta / f"{categoria}{marca}-{proximo:02d}.jpg"
            normalizar(p, saida, largura, qualidade)
            guardados.mkdir(exist_ok=True)
            p.rename(guardados / p.name)      # convertido é convertido: não se converte de novo
            print(f"  {p.name} → {saida.name}")
        arquivos = sorted(p.name for p in pasta.glob(f"{categoria}*-[0-9][0-9].jpg"))
        pool[categoria] = [f"/acervo/{categoria}/{n}" for n in arquivos]
        total += len(arquivos)
        print(f"{categoria}: {len(arquivos)} foto(s)")
    if not PROCEDENCIA.exists():
        PROCEDENCIA.write_text(MODELO_PROCEDENCIA, encoding="utf-8")
    DESTINO.write_text(json.dumps(pool, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{total} foto(s) em {DESTINO.relative_to(RAIZ)}")
    if total:
        print("Agora regere o acervo: python scripts/gerar_imoveis.py")
    else:
        print("Nenhuma foto encontrada — o acervo seguirá com as URLs de exemplo.\n"
              f"Coloque os arquivos em {ORIGEM.relative_to(RAIZ)}/<categoria>/ e rode de novo.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--largura", type=int, default=1200)
    p.add_argument("--qualidade", type=int, default=78)
    a = p.parse_args()
    main(a.largura, a.qualidade)
