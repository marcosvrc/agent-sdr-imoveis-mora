# Equipe de demonstração

`corretores.json` é a **fonte única** da equipe simulada: `scripts/semear_corretores.py` cria estes
corretores na Mora (tabela `corretores`) e o seed do CRM cria os mesmos como `users` com papel
`broker`. O vínculo entre os dois lados é o **e-mail** — é por ele que
`semear_corretores.py --vincular-crm` preenche `crm_user_id`, que é o que faz o encaminhamento subir
com destinatário.

Mesmo motivo do acervo estar num arquivo só (ver `data/imoveis/README.md`): duas listas de equipe,
uma em cada serviço, descreveriam a mesma imobiliária com pessoas diferentes, e o encaminhamento não
encontraria ninguém do outro lado.

## Campos

| Campo | Para que serve |
|---|---|
| `id` | id na Mora — mesma regra de slug do `POST /corretores` (`cor_nome-sobrenome`) |
| `nome` | exibido no painel e no CRM; o avatar é desenhado com as iniciais |
| `email` | **a chave entre os dois sistemas**; `example.com` é reservado pela RFC 2606 para exemplos |
| `telefone` | convenção de número falso do projeto (`5511999990000`+), não é faixa reservada |
| `regioes` | usada no encaminhamento por região; distribuição desigual de propósito |
| `ativo` | dois inativos, para exercitar carteira e desligamento |

## O que não existe aqui, e por quê

**CRECI.** Não há campo de registro profissional em nenhum banco do projeto, e este arquivo não
inventa um: credencial fabricada dentro de um sistema que conversa com cliente é outra categoria de
problema. No site institucional o CRECI aparece como placeholder visivelmente marcado
(`apps/web/src/lib/imobiliaria.ts`).

**Foto.** Sem foto de propósito — retrato de pessoa inventada seria foto de alguém real usada
indevidamente ou rosto sintético passando por corretor. O painel desenha o avatar com as iniciais
quando `foto` é nulo.

Pessoas fictícias. Qualquer semelhança com nome de pessoa real é coincidência, e nenhum dado aqui
foi coletado de ninguém.

## Como usar

```bash
make crm-seed                                        # cria os `users` no CRM
python scripts/semear_corretores.py --vincular-crm   # cria na Mora e casa por e-mail
python scripts/semear_corretores.py --listar         # confere
```
