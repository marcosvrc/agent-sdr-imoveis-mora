import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import { ErroApi } from "./lib/api";
import { marcarSessaoExpirada } from "./lib/sessao";
import "./index.css";

// `retry: false` de propósito: a API devolve erro de NEGÓCIO com código estável (contato
// bloqueado, versão vencida, qualificação incompleta). Repetir isso não muda nada e só atrasa a
// mensagem que a pessoa precisa ler.
//
// 401 em QUALQUER consulta ou ação (não só no `eu`) quer dizer que a sessão caiu com a tela aberta:
// marca a expiração e refaz o `eu`, que então responde 401 e o App mostra o login com o aviso.
// O 401 do próprio `eu` é o estado normal de quem ainda não entrou — esse não é "expirou".
function aoFalhar(erro: unknown, chave?: readonly unknown[]) {
  if (!(erro instanceof ErroApi) || erro.status !== 401 || chave?.[0] === "eu") return;
  marcarSessaoExpirada();
  void cliente.resetQueries({ queryKey: ["eu"] });
}

const cliente: QueryClient = new QueryClient({
  queryCache: new QueryCache({ onError: (erro, consulta) => aoFalhar(erro, consulta.queryKey) }),
  mutationCache: new MutationCache({ onError: (erro) => aoFalhar(erro) }),
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false, staleTime: 10_000 } },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={cliente}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
