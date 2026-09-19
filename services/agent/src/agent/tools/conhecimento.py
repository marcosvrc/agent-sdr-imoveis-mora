"""RAG institucional: responde "como a imobiliária trabalha" a partir dos documentos dela.

Mesma arquitetura híbrida do `buscar_imoveis` (ADR-0001): Knowledge Base do Bedrock quando existe,
pgvector direto no perfil local. A diferença está no que se faz com um resultado ruim.

Na busca de imóveis, trazer algo parecido é útil — "no bairro pedido não tenho, mas tenho aqui do
lado" é uma boa resposta. Aqui não: trazer o trecho mais próximo de uma pergunta que o corpus não
cobre produz uma afirmação **falsa sobre a política da empresa**, dita com a confiança de quem leu
um documento. Por isso a busca institucional tem piso de similaridade e devolve lista vazia sem
constrangimento — "não sei, o corretor confirma" é uma resposta correta; inventar a taxa não é.
"""
from sdr_shared.conhecimento import (PISO_SIMILARIDADE, Trecho, acima_do_piso,
                                     reescrever_pergunta)
from sdr_shared.config import get_settings
from sdr_shared.db import DocumentoRepository

LIMITE = 3          # três trechos cabem no prompt e cobrem a pergunta composta ("taxa e prazo?")


def _via_knowledge_base(pergunta: str, limite: int) -> list[Trecho]:
    import boto3
    s = get_settings()
    r = boto3.client("bedrock-agent-runtime", region_name=s.aws_region).retrieve(
        knowledgeBaseId=s.knowledge_base_id, retrievalQuery={"text": pergunta},
        retrievalConfiguration={"vectorSearchConfiguration": {
            "numberOfResults": limite,
            # A KB de imóveis e a de documentos convivem na mesma base; sem este filtro a pergunta
            # sobre taxa traria um anúncio de apartamento como "fonte".
            "filter": {"equals": {"key": "tipo", "value": "documento"}}}})
    trechos = []
    for x in r["retrievalResults"]:
        meta = x.get("metadata", {})
        trechos.append(Trecho(
            id=str(meta.get("id", meta.get("x-amz-bedrock-kb-source-uri", ""))),
            arquivo=str(meta.get("arquivo", "")), assunto=str(meta.get("assunto", "geral")),
            titulo=meta.get("titulo"), texto=x["content"]["text"], ordem=int(meta.get("ordem", 0)),
            # A KB devolve score em escala própria; o piso é aplicado sobre ele do mesmo jeito.
            score=float(x.get("score", 0.0))))
    return trechos


def consultar(pergunta: str, limite: int = LIMITE, piso: float = PISO_SIMILARIDADE,
              anteriores: list[str] | None = None) -> list[Trecho]:
    """Trechos institucionais relevantes para a pergunta, ou lista vazia.

    Lista vazia não é erro: é o caso em que a base não cobre o assunto, e quem chama precisa dizer
    isso ao cliente em vez de improvisar.

    `anteriores` são as falas anteriores do CLIENTE. Servem para reescrever uma pergunta que não se
    sustenta sozinha: "e se eu sair antes?" não tem assunto nenhum para um embedding, e sem a
    reescrita ela vira uma consulta vaga — à qual a busca vetorial responde com o vizinho mais
    próximo de coisa alguma.
    """
    pergunta = reescrever_pergunta(pergunta, anteriores)
    if not pergunta:
        return []
    if get_settings().knowledge_base_id:
        return acima_do_piso(_via_knowledge_base(pergunta, limite), piso)

    from sdr_shared.ports import get_embedder
    try:
        vetor = get_embedder().embed(pergunta)
    except Exception:
        # Embedder fora do ar (Ollama caiu, Bedrock sem credencial): sem vetor não há busca. Devolver
        # vazio faz o nó cair no "não sei" e oferecer o corretor — que é degradar, não quebrar.
        return []
    return acima_do_piso(DocumentoRepository().buscar(vetor, limite), piso)

