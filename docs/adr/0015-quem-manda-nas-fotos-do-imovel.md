---
title: "ADR-0015: Quem manda nas fotos do imóvel"
description: Por que existem duas fontes de foto, qual vence, e por que resolver isso com "agindo em nome de" no CRM seria gastar a garantia mais forte do projeto no problema mais fraco.
---

# ADR-0015 — Quem manda nas fotos do imóvel

**Status:** aceito · **Data:** 2026-09 · **Escopo:** `apps/dashboard`, `services/api`, `services/crm`, `services/ingestion`

## Contexto

Foto de imóvel é a única informação do acervo que hoje tem **duas origens**, e elas nasceram em
momentos diferentes por motivos diferentes.

A primeira é o **painel da Mora**: o navegador reduz a imagem, manda em base64, a API grava em
`fotos_dir/<imovel>/<uuid>.jpg` e guarda o caminho relativo `/fotos/...` na tabela `imoveis` — que é
o índice do agente. Existe envio, remoção e troca de capa. Funciona, e é o caminho que um corretor
usa de verdade: ele tira a foto no celular.

A segunda é o **CRM**, e entrou depois, quando o cadastro de imóvel ganhou tela. Sem fotos ali, todo
imóvel cadastrado pelo CRM nasceria mudo na vitrine enquanto os do seed apareciam — duas regras
diferentes para a mesma coisa, decididas por quem criou o registro.

O binário nunca esteve no banco, e isso é deliberado: o CRM divide o Postgres com o agente, e uma
leitura de imagem ocuparia conexão do pool que deveria estar atendendo conversa, além de entrar em
todo backup. O que as duas fontes guardam é **referência**.

### O erro de análise que antecedeu esta decisão

Vale registrar porque ele explica por que esta ADR existe. Ao discutir onde gravar imagem, foi
afirmado que "o sistema nunca guardou um byte de imagem, só referência" — **falso**, o painel já
tinha o envio completo. E, ao descobrir a segunda origem, foi afirmado que o resultado "depende de
qual regra roda primeiro" — **também falso**. As duas conclusões vieram de leitura de código; a
medição desmentiu as duas.

## Decisão

### 1. A ordem é painel > CRM > arquivo, e ela é determinística

Não é ambiguidade tolerada: é o comportamento medido, e ele é estável.

1. `sdr_ingestion/acervo.py` monta o imóvel com as fotos do CRM, caindo no arquivo do acervo quando
   o CRM não tem nenhuma (`fotos or extra.fotos`);
2. `ImovelRepository.upsert` fala por último, e protege o que veio do painel:

```sql
fotos = CASE WHEN EXISTS (SELECT 1 FROM jsonb_array_elements_text(imoveis.fotos) f
                           WHERE f LIKE '/fotos/%')
             THEN imoveis.fotos ELSE EXCLUDED.fotos END
```

Como o `CASE` é a última palavra, foto enviada pelo painel sobrevive a qualquer reindexação. O
efeito prático: **enquanto houver upload do painel para aquele imóvel, o CRM não aparece.**

A ordem está presa em `shared/tests/test_acervo_do_crm.py`. Ela é emergente — nasce de duas regras
escritas em arquivos diferentes — e mudar em silêncio significa foto de imóvel sumindo da vitrine
sem ninguém saber por quê. O teste é o que impede isso.

### 2. O arquivo do acervo continua como reserva

Imóvel cadastrado antes de as fotos virarem registro do CRM não perde a vitrine porque a fonte
mudou. Reserva, e não fonte: quando CRM ou painel têm foto, o arquivo cala.

### 3. Não haverá "agindo em nome de" no CRM

A alternativa aparentemente óbvia — o painel envia o arquivo e grava a referência no CRM — **não é
implementável sem quebrar uma garantia**, e a descoberta veio tarde:

`PUT /v1/properties/{id}/photos` exige `exigir_humano`, e no CRM `humano` significa
`tipo == "user"`: sessão de corretor ou administrador. O backend do agente tem credencial de
**serviço**. Para ele gravar, seria preciso dar-lhe identidade humana no CRM ou criar um conceito de
"agindo em nome de".

Os dois enfraquecem exatamente a trava que impede o agente de escrever no acervo — a mesma que
recusa cadastro de imóvel vindo de uma conversa, porque seria o caminho mais curto para um anúncio
inventado. É a garantia mais forte do projeto, e o problema que ela resolveria aqui é **envio de
foto**. Trocar uma pela outra é mau negócio.

## Consequências

**A favor**

- Zero trabalho e zero risco: é o comportamento que já existe, agora documentado e testado.
- A trava `exigir_humano` continua absoluta: nenhuma credencial de serviço escreve no acervo.
- Os dois caminhos de cadastro funcionam — quem cadastra pelo CRM põe URL, quem usa o painel envia
  arquivo.

**Contra, e assumido**

- **Duas fontes.** Quem editar as fotos pelo CRM num imóvel que já tem upload do painel não verá
  efeito nenhum, e a tela não avisa. É a consequência mais desconfortável desta decisão, e ela é
  real: o silêncio só não vira defeito porque o caso ainda não aconteceu.
- **A ordem só é óbvia para quem lê o teste ou esta ADR.** Não há nada na interface que a explique.
- O painel grava no índice do agente, que é uma cópia derivada — conceitualmente errado, e
  funcionando por causa de um `CASE` escrito de propósito.

## Alternativas consideradas

**Mover o upload para o CRM e tirar a tela do painel.** É a saída correta para fonte única, e não
toca na trava: o CRM recebe o arquivo, serve a imagem e passa a ser dono de tudo. Ficou de fora
agora porque é reescrita de algo que funciona, em troca de coerência — e há trabalho de maior
retorno na frente. **É o caminho recomendado quando a fonte única for necessária.**

**"Agindo em nome de" no CRM**, usando o `corretores.crm_user_id` que já existe como ponte. É o mais
completo e o que mais custa: cria uma via pela qual uma credencial de serviço age como humano, e
essa via não fica restrita a fotos depois de existir. Recusado pelo motivo da seção 3.

**Voltar atrás e tirar as fotos do CRM.** Devolveria a fonte única imediatamente, ao preço de imóvel
cadastrado pelo CRM nascer mudo na vitrine — que é o defeito que motivou acrescentá-las.
