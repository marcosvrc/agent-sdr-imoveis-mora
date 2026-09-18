# Painel do CRM

Interface do corretor e do administrador para o CRM sintético. React + TypeScript + Vite.

```bash
npm install
VITE_CRM_API=http://localhost:8100 npm run dev     # http://localhost:3000
```

**Use o mesmo host nos dois lados.** `localhost` e `127.0.0.1` são sites diferentes para o
navegador: com o painel em um e a API no outro, o login devolve 200 e o cookie de sessão não é
guardado. O painel detecta isso e explica, mas o certo é não cair nele.

A senha de acesso é gerada pelo seed do CRM e impressa uma única vez:

```bash
cd ../../services/crm && python -m sdr_crm.seed --seed 42
```

## O que existe

| Tela | Para quê |
| --- | --- |
| Visão geral | O que exige ação hoje (fila, tarefas vencidas, visitas a confirmar) e o funil |
| Funil | Quadro por estágio; mudança por menu acessível, com motivo quando a regra exige |
| Clientes | Busca por nome (procura) e por identificador (identifica); ficha com linha do tempo |
| Oportunidade | Preferências, imóveis, visitas, tarefas e quem está conduzindo |
| Imóveis | Catálogo com custo discriminado; total desconhecido aparece como **incompleto** |
| Visitas | Confirmar, concluir, marcar falta e cancelar — tudo humano |
| Encaminhamentos | Fila, aceite e resolução com escolha explícita de quem continua |
| Auditoria | Somente administrador; somente leitura |

## Regras que a interface respeita

- **Esconder botão não é controle de acesso.** Quem recusa é a API; a tela só evita oferecer o que
  vai falhar.
- **Nada de sucesso antes da resposta.** O botão fica ocupado até o servidor confirmar, e em erro o
  estado volta ao que era.
- **Loading, vazio e erro em toda consulta.** Tela em branco carregando e tela em branco por não
  haver nada pedem reações opostas.
- **Faixa permanente de ambiente de testes**, que não fecha e não some ao rolar.

Verificado com axe-core (WCAG 2.1 AA) em sete telas: zero violações.
