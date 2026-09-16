import { Link } from "react-router-dom";
import { IMOBILIARIA } from "../lib/imobiliaria";
import { useSeo } from "../lib/seo";
import { Migalha } from "../components/Migalha";
import { DadoInstitucional } from "../components/Confianca";

/** Aviso de privacidade (LGPD).
 *
 *  Descreve o que o sistema realmente faz — sessão assinada, eventos de navegação, favoritos no
 *  navegador, dados de contato coletados na conversa e repassados ao corretor. Nenhuma frase aqui é
 *  boilerplate: cada item corresponde a um mecanismo que existe no código (ver `lib/tracking.ts`,
 *  `lib/session.ts`, `store/favoritos.ts` e o `handler` do agente).
 *
 *  O encarregado (DPO) e os canais de contato são placeholders enquanto não houver empresa real.
 */
export function Privacidade() {
  useSeo({
    titulo: "Privacidade e uso de dados | Vértice Imóveis",
    descricao: "Quais dados a Vértice Imóveis coleta neste site, para que usa, por quanto tempo guarda e como você exerce seus direitos previstos na LGPD.",
    caminho: "/privacidade",
  });

  return (
    <div className="mx-auto max-w-3xl px-4 py-6 sm:px-6">
      <Migalha itens={[{ rotulo: "Início", para: "/" }, { rotulo: "Privacidade" }]} />
      <h1 className="mt-3 font-display text-2xl font-semibold text-brand sm:text-3xl">Privacidade e uso de dados</h1>
      <p className="mt-2 text-sm text-ink-muted">
        Este aviso explica, em linguagem direta, o que acontece com seus dados quando você navega
        aqui ou conversa com a Mora. Ele segue a Lei Geral de Proteção de Dados (Lei 13.709/2018).
      </p>

      <div className="mt-8 space-y-8 text-ink-muted">
        <Bloco titulo="O que coletamos, e quando">
          <Lista itens={[
            ["Enquanto você navega", "um identificador de sessão assinado pelo nosso servidor, e quais imóveis você abriu ou filtrou. Serve para que a Mora já saiba do que você estava olhando quando você abrir a conversa."],
            ["Quando você favorita um imóvel", "a lista fica no seu próprio navegador. Não sobe para nossos servidores e some se você limpar os dados do site."],
            ["Quando você conversa com a Mora", "o conteúdo das mensagens e, se você quiser agendar uma visita, seu nome, telefone e e-mail."],
          ]} />
          <p className="mt-3">
            Não usamos cookies de publicidade, não há rastreador de terceiros e não vendemos nem
            compartilhamos seus dados com anunciantes.
          </p>
        </Bloco>

        <Bloco titulo="Para que usamos">
          <Lista itens={[
            ["Atendimento", "entender o que você procura, sugerir imóveis do nosso catálogo e marcar visitas."],
            ["Continuidade", "se você começar no site e continuar no Telegram, o atendimento segue de onde parou."],
            ["Qualidade e segurança", "registros técnicos do atendimento, usados para corrigir falhas e conter abuso."],
          ]} />
          <p className="mt-3">
            A base legal é o <strong>legítimo interesse</strong> para a navegação, e a <strong>execução
            de diligências pré-contratuais a seu pedido</strong> quando você entrega contato para agendar
            uma visita. Você não é obrigado a informar nada para navegar pelo catálogo.
          </p>
        </Bloco>

        <Bloco titulo="Decisões automatizadas">
          <p>
            A Mora é um assistente virtual. Ela interpreta o que você escreve, classifica o interesse
            (por exemplo, urgência e faixa de preço) e sugere imóveis. Nenhuma dessas classificações
            nega serviço a ninguém, e <strong>você pode pedir um corretor humano a qualquer momento</strong> —
            basta escrever isso na conversa. É o direito de revisão previsto no art. 20 da LGPD.
          </p>
        </Bloco>

        <Bloco titulo="Por quanto tempo guardamos">
          <Lista itens={[
            ["Conversas e dados de contato", "enquanto durar o atendimento e o relacionamento comercial."],
            ["Eventos de navegação", "período curto, apenas para dar contexto à conversa em andamento."],
            ["Favoritos", "ficam com você, no navegador, até que você os apague."],
          ]} />
        </Bloco>

        <Bloco titulo="Com quem compartilhamos">
          <p>
            Com os corretores da {IMOBILIARIA.nome.valor} responsáveis pelo seu atendimento, e com os
            provedores de tecnologia que hospedam o sistema e processam a conversa do assistente. Esses
            provedores tratam os dados sob contrato e apenas para prestar o serviço.
          </p>
        </Bloco>

        <Bloco titulo="Seus direitos">
          <p>
            Você pode pedir confirmação de tratamento, acesso, correção, anonimização, portabilidade ou
            eliminação dos seus dados, além de revogar consentimento. É só pedir pelos canais abaixo —
            respondemos no prazo legal.
          </p>
          <div className="mt-3 rounded-lg bg-surface p-4 ring-1 ring-line">
            <p className="text-sm font-medium text-ink">Encarregado pelo tratamento de dados</p>
            <p className="mt-1 text-sm"><DadoInstitucional campo={IMOBILIARIA.email} /></p>
            <p className="text-sm"><DadoInstitucional campo={IMOBILIARIA.telefone} /></p>
            <p className="text-sm"><DadoInstitucional campo={IMOBILIARIA.endereco} /></p>
          </div>
        </Bloco>

        <Bloco titulo="Como apagar o que está no seu navegador">
          <p>
            Os favoritos e o histórico de imóveis vistos ficam só no seu aparelho. Você pode limpar os
            favoritos em <Link to="/favoritos" className="font-medium text-brand-accentDark hover:underline">Meus favoritos</Link>,
            o histórico pelo botão “Limpar histórico” na seção de imóveis vistos, ou apagar tudo de uma
            vez limpando os dados deste site no seu navegador.
          </p>
        </Bloco>
      </div>

      <p className="mt-10 rounded-lg border border-dashed border-amber-400 bg-amber-50 p-4 text-xs text-estado-alerta">
        Aviso: este é um projeto acadêmico de demonstração. Os dados de contato, CNPJ e registro
        profissional exibidos no site são exemplos, e não correspondem a uma empresa real.
      </p>
    </div>
  );
}

function Bloco({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="font-display text-xl font-semibold text-brand">{titulo}</h2>
      <div className="mt-2 space-y-2 leading-relaxed">{children}</div>
    </section>
  );
}

function Lista({ itens }: { itens: [string, string][] }) {
  return (
    <ul className="mt-2 space-y-2">
      {itens.map(([t, d]) => (
        <li key={t} className="flex gap-2">
          <span aria-hidden className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-accent" />
          <span><strong className="font-medium text-ink">{t}:</strong> {d}</span>
        </li>
      ))}
    </ul>
  );
}
