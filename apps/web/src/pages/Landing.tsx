import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { buscarImoveis } from "../lib/api";
import { organizacaoJsonLd, IMOBILIARIA } from "../lib/imobiliaria";
import { useSeo } from "../lib/seo";
import { BotaoLink, Botao, EstadoErro, Secao } from "../lib/ui";
import { BuscaHero } from "../components/BuscaHero";
import { ComoFunciona } from "../components/ComoFunciona";
import { FaixaGarantias } from "../components/Confianca";
import { CtaTelegram } from "../components/CtaTelegram";
import { ImovelCard } from "../components/ImovelCard";
import { SkeletonCard } from "../components/SkeletonCard";
import { VistosRecentemente } from "../components/VistosRecentemente";
import { Ic } from "../components/Icones";
import { useChat } from "../store/chat";

export function Landing() {
  const abrirChat = useChat((s) => s.abrir);

  // 6 destaques = 6 imóveis pedidos. Antes a home baixava os 200 do catálogo para mostrar seis.
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["destaques"],
    queryFn: () => buscarImoveis({}, "relevancia", 6, 0),
    staleTime: 5 * 60_000,
  });

  useSeo({
    titulo: "Vértice Imóveis — apartamentos e casas em São Paulo",
    descricao: "Compra e aluguel de imóveis em São Paulo com atendimento imediato: converse com a Mora, receba sugestões do catálogo e agende a visita sem espera.",
    caminho: "/",
    jsonLd: [organizacaoJsonLd(), {
      "@context": "https://schema.org", "@type": "WebSite",
      name: IMOBILIARIA.nome.valor,
      potentialAction: {
        "@type": "SearchAction",
        target: { "@type": "EntryPoint", urlTemplate: "/imoveis?texto={search_term_string}" },
        "query-input": "required name=search_term_string",
      },
    }],
  });

  return (
    <div>
      <section className="relative overflow-hidden bg-brand">
        <div aria-hidden className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(37,99,235,0.35),transparent_45%),radial-gradient(circle_at_85%_75%,rgba(37,99,235,0.25),transparent_40%)]" />
        <div className="relative mx-auto grid max-w-6xl gap-10 px-4 py-14 sm:px-6 sm:py-20 md:grid-cols-2 md:items-center">
          <div className="animate-fade-up space-y-5 text-white">
            <p className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs font-medium text-blue-50">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" aria-hidden />
              Mora responde agora, 24h por dia
            </p>
            <h1 className="font-display text-3xl font-semibold leading-tight sm:text-4xl md:text-5xl">
              Encontre seu imóvel em São Paulo <span className="text-blue-200">conversando</span>.
            </h1>
            <p className="font-display text-lg text-blue-100 sm:text-xl">{IMOBILIARIA.slogan.valor}</p>
            <p className="max-w-md text-blue-50/90">
              Diga o que procura à Mora: ela busca no catálogo da {IMOBILIARIA.nome.valor}, explica por que
              cada imóvel combina com você e agenda a visita — sem fila e sem formulário.
            </p>
            <div className="flex flex-wrap gap-3 pt-1">
              <Botao variante="contraste" tamanho="lg" icone={<Ic.chat size={18} />} onClick={() => abrirChat()}>
                Conversar com a Mora
              </Botao>
              <BotaoLink para="/imoveis" tamanho="lg" variante="fantasma"
                         className="border border-white/30 text-white hover:bg-white/10 hover:text-white">
                Ver todos os imóveis
              </BotaoLink>
            </div>
          </div>
          <div className="animate-fade-up [animation-delay:100ms]"><BuscaHero /></div>
        </div>
      </section>

      <div className="border-y border-line bg-surface">
        <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
          <FaixaGarantias />
        </div>
      </div>

      <Secao titulo="Imóveis em destaque"
             descricao="Uma amostra do catálogo — a Mora conhece todos, inclusive os que não aparecem aqui."
             acao={<Link to="/imoveis" className="hidden shrink-0 text-sm font-semibold text-brand-accentDark hover:underline sm:inline-flex sm:items-center sm:gap-1">Ver catálogo completo <Ic.seta size={15} /></Link>}>
        {/* Seção sem estado de falha era a pior versão do problema: a home simplesmente exibia um
            buraco quando a API não respondia, e nada dizia ao visitante o que tinha acontecido. */}
        {error ? (
          <EstadoErro descricao="Não conseguimos carregar os destaques agora." aoTentar={() => refetch()} />
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {isLoading
              ? Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} />)
              : data?.itens.map((im, i) => <ImovelCard key={im.id} im={im} prioridade={i < 3} />)}
          </div>
        )}
        <BotaoLink para="/imoveis" variante="secundario" largo className="mt-6 sm:hidden">Ver catálogo completo</BotaoLink>
      </Secao>

      <ComoFunciona />

      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <VistosRecentemente titulo="Você viu recentemente" />
      </div>

      <Secao titulo="Prefere continuar no Telegram?"
             descricao="A Mora é a mesma assistente nos dois canais: comece aqui e continue por lá sem repetir nada — seu atendimento segue de onde parou.">
        <div className="flex flex-wrap gap-3">
          <CtaTelegram tamanho="lg" />
          <Botao variante="secundario" tamanho="lg" icone={<Ic.chat size={17} />} onClick={() => abrirChat()}>
            Ou converse aqui mesmo
          </Botao>
        </div>
      </Secao>
    </div>
  );
}
