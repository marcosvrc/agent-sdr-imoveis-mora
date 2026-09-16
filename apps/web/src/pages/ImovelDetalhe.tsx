import { useEffect, useMemo } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { REGIOES, TIPOS, brl, buscarImoveis, nomeImovel, obterImovel, type Imovel } from "../lib/api";
import { caminhoImovel, idDoSlug } from "../lib/slug";
import { SITE, trilhaJsonLd, useSeo } from "../lib/seo";
import { registrarVisto } from "../lib/vistos";
import { IMOBILIARIA } from "../lib/imobiliaria";
import { Botao, Cartao, EstadoErro, Esqueleto, Selo } from "../lib/ui";
import { CtaTelegram } from "../components/CtaTelegram";
import { GaleriaFotos } from "../components/GaleriaFotos";
import { FavoritoBotao } from "../components/FavoritoBotao";
import { Migalha } from "../components/Migalha";
import { ImovelCard } from "../components/ImovelCard";
import { SkeletonCard } from "../components/SkeletonCard";
import { CustoMensal, SimulacaoFinanciamento } from "../components/CustoESimulacao";
import { BarraCtaMobile } from "../components/BarraCtaMobile";
import { Compartilhar } from "../components/Compartilhar";
import { VistosRecentemente } from "../components/VistosRecentemente";
import { DadoInstitucional } from "../components/Confianca";
import { Ic } from "../components/Icones";
import { track } from "../lib/tracking";
import { useChat } from "../store/chat";

const resumo = (im: Imovel) => ({ id: im.id, tipo: im.tipo, bairro: im.bairro, operacao: im.operacao, preco: im.preco });

export function ImovelDetalhe() {
  const { slug = "" } = useParams();
  const id = idDoSlug(slug);
  const abrirChat = useChat((s) => s.abrir);

  const { data: im, isLoading, error, refetch } = useQuery({
    queryKey: ["imovel", id], queryFn: () => obterImovel(id!), enabled: !!id,
  });

  // Parecidos vêm filtrados do servidor (mesmo bairro, mesma operação) — antes o site baixava os
  // 200 imóveis do catálogo e filtrava no navegador.
  const { data: parecidos } = useQuery({
    queryKey: ["parecidos", im?.bairro, im?.operacao],
    queryFn: () => buscarImoveis({ bairro: im!.bairro, operacao: im!.operacao }, "relevancia", 4, 0),
    enabled: !!im,
  });

  useEffect(() => { if (id) { track("viewed_imovel", { imovel_id: id }); registrarVisto(id); } }, [id]);

  const semelhantes = useMemo(() => (parecidos?.itens ?? []).filter((o) => o.id !== im?.id).slice(0, 3), [parecidos, im]);

  useSeo({
    titulo: im ? `${nomeImovel(im)} — ${brl(im.preco)}${im.operacao === "aluguel" ? "/mês" : ""} | Vértice Imóveis`
               : "Imóvel | Vértice Imóveis",
    descricao: im ? `${nomeImovel(im)}, ${im.area_m2} m²${im.vagas ? `, ${im.vagas} vaga(s)` : ""}, em ${im.bairro}, ${im.cidade}. ${im.descricao}`.slice(0, 300)
                  : "Ficha do imóvel.",
    caminho: im ? caminhoImovel(im) : undefined,
    imagem: im?.fotos[0],
    tipo: "article",
    jsonLd: im ? [fichaJsonLd(im), trilhaJsonLd([
      { nome: "Início", caminho: "/" },
      { nome: "Imóveis", caminho: "/imoveis" },
      { nome: im.bairro, caminho: `/imoveis/${im.operacao}/${im.bairro.toLowerCase().replace(/\s+/g, "-")}` },
      { nome: nomeImovel(im), caminho: caminhoImovel(im) },
    ])] : undefined,
  }, [im?.id]);

  if (!id) return <Navigate to="/imoveis" replace />;

  if (error) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16 sm:px-6">
        <EstadoErro titulo="Não encontramos este imóvel"
                    descricao="Ele pode ter saído do catálogo. Veja opções parecidas ou pergunte à Mora."
                    aoTentar={() => refetch()} />
        <div className="mt-4 text-center">
          <Link to="/imoveis" className="text-sm font-semibold text-brand-accentDark hover:underline">Ver catálogo completo</Link>
        </div>
      </div>
    );
  }

  if (isLoading || !im) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        <div className="grid gap-8 md:grid-cols-5">
          <div className="space-y-4 md:col-span-3">
            <Esqueleto className="aspect-[4/3] w-full" />
            <Esqueleto className="h-8 w-2/3" /><Esqueleto className="h-5 w-1/3" />
            <Esqueleto className="h-24 w-full" />
          </div>
          <div className="md:col-span-2"><Esqueleto className="h-64 w-full" /></div>
        </div>
      </div>
    );
  }

  const aluguel = im.operacao === "aluguel";
  const atributos = [
    { i: <Ic.cama size={18} />, r: "Quartos", v: im.quartos },
    { i: <Ic.banho size={18} />, r: "Suítes", v: im.suites },
    { i: <Ic.carro size={18} />, r: "Vagas", v: im.vagas },
    { i: <Ic.regua size={18} />, r: "Área", v: `${im.area_m2} m²` },
  ];

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 pb-28 sm:px-6 md:pb-8">
      <Migalha itens={[
        { rotulo: "Início", para: "/" },
        { rotulo: "Imóveis", para: "/imoveis" },
        { rotulo: im.bairro, para: `/imoveis?bairro=${encodeURIComponent(im.bairro)}` },
        { rotulo: nomeImovel(im) },
      ]} />

      <div className="mt-3 grid gap-8 md:grid-cols-5">
        <div className="space-y-6 md:col-span-3">
          <GaleriaFotos fotos={im.fotos} alt={nomeImovel(im)} />

          <header>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <Selo tom={aluguel ? "info" : "marca"}>{aluguel ? "Aluguel" : "Venda"}</Selo>
                  {im.destaque_investimento && <Selo tom="alerta">Indicado para investir</Selo>}
                  <span className="text-xs uppercase tracking-wide text-ink-soft">
                    {TIPOS[im.tipo] ?? im.tipo} · {REGIOES[im.regiao] ?? im.regiao}
                  </span>
                </div>
                <h1 className="mt-2 font-display text-2xl font-semibold text-brand sm:text-3xl">{nomeImovel(im)}</h1>
                <p className="mt-1 inline-flex items-center gap-1.5 text-sm text-ink-muted">
                  <Ic.local size={15} />{im.bairro}, {im.cidade}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Compartilhar titulo={nomeImovel(im)} texto={`${nomeImovel(im)} — ${brl(im.preco)}`} />
                <FavoritoBotao id={im.id} nome={nomeImovel(im)} className="ring-1 ring-line" />
              </div>
            </div>

            <p className="mt-4 font-display text-3xl font-semibold text-brand">
              {brl(im.preco)}{aluguel && <span className="font-sans text-base font-normal text-ink-muted">/mês</span>}
            </p>
            {im.condominio != null && im.condominio > 0 && (
              <p className="text-sm text-ink-muted">+ condomínio {brl(im.condominio)}/mês</p>
            )}
          </header>

          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {atributos.map((a) => (
              <li key={a.r} className="rounded-md bg-surface p-3 text-center ring-1 ring-line">
                <span className="mx-auto grid h-8 w-8 place-items-center text-ink-muted" aria-hidden>{a.i}</span>
                <span className="mt-1 block font-semibold text-ink">{a.v}</span>
                <span className="block text-xs text-ink-muted">{a.r}</span>
              </li>
            ))}
          </ul>

          <section aria-labelledby="sobre">
            <h2 id="sobre" className="font-semibold text-ink">Sobre o imóvel</h2>
            <p className="mt-2 whitespace-pre-wrap leading-relaxed text-ink-muted">{im.descricao}</p>
          </section>

          {!!im.pontos_referencia?.length && (
            <section aria-labelledby="perto">
              <h2 id="perto" className="font-semibold text-ink">O que tem por perto</h2>
              <ul className="mt-2 flex flex-wrap gap-2">
                {im.pontos_referencia.map((p) => (
                  <li key={p} className="inline-flex items-center gap-1.5 rounded-full bg-brand-suave px-3 py-1.5 text-sm capitalize text-brand-accentDark">
                    <Ic.local size={14} />{p}
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-ink-muted">
                Referências do bairro. O endereço exato é informado pelo corretor no agendamento da visita.
              </p>
            </section>
          )}

          <CustoMensal im={im} />
          <SimulacaoFinanciamento im={im} />
        </div>

        <aside className="md:col-span-2">
          <Cartao className="sticky top-20 space-y-3 p-4">
            <p className="font-semibold text-ink">Interessado neste imóvel?</p>
            <p className="text-sm text-ink-muted">
              A Mora responde na hora, tira dúvidas sobre o imóvel e agenda a visita. Um corretor
              assume a conversa sempre que você pedir.
            </p>
            <Botao largo tamanho="lg" icone={<Ic.chat size={18} />}
                   onClick={() => abrirChat(im.id, resumo(im))}>
              Falar sobre este imóvel
            </Botao>
            <CtaTelegram imovelId={im.id} largo />
            <div className="border-t border-line pt-3 text-xs text-ink-muted">
              <p className="mb-1 font-medium text-ink">Atendimento</p>
              <p><DadoInstitucional campo={IMOBILIARIA.creci} /></p>
              <p className="mt-1"><DadoInstitucional campo={IMOBILIARIA.horario} /></p>
              <p className="mt-2">Ao iniciar a conversa, seus dados são usados apenas para este atendimento.{" "}
                <Link to="/privacidade" className="underline underline-offset-2 hover:text-ink">Saiba como</Link>.
              </p>
            </div>
          </Cartao>
        </aside>
      </div>

      {semelhantes.length > 0 && (
        <section aria-labelledby="parecidos" className="mt-14">
          <h2 id="parecidos" className="font-display text-xl font-semibold text-brand sm:text-2xl">
            Outros imóveis {aluguel ? "para alugar" : "à venda"} em {im.bairro}
          </h2>
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {semelhantes.map((p) => <ImovelCard key={p.id} im={p} />)}
          </div>
        </section>
      )}
      {!parecidos && (
        <div className="mt-14 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
      )}

      <VistosRecentemente excluir={im.id} />

      {/* Barra fixa só no celular: no desktop o cartão lateral já acompanha a rolagem. */}
      <BarraCtaMobile im={im} aoConversar={() => abrirChat(im.id, resumo(im))} />
    </div>
  );
}

/** Dado estruturado da ficha.
 *
 *  `RealEstateListing` é o tipo que os buscadores entendem para anúncio de imóvel; `offers` com
 *  preço e moeda é o que permite o resultado rico mostrar o valor. Só entram campos que existem no
 *  cadastro — nada de disponibilidade ou avaliação inventada. */
function fichaJsonLd(im: Imovel) {
  return {
    "@context": "https://schema.org",
    "@type": "RealEstateListing",
    name: nomeImovel(im),
    description: im.descricao,
    url: SITE + caminhoImovel(im),
    ...(im.fotos.length ? { image: im.fotos } : {}),
    offers: {
      "@type": "Offer",
      price: im.preco,
      priceCurrency: "BRL",
      availability: "https://schema.org/InStock",
      ...(im.operacao === "aluguel" ? { businessFunction: "http://purl.org/goodrelations/v1#LeaseOut" } : {}),
    },
    about: {
      "@type": im.tipo === "casa" ? "House" : "Apartment",
      numberOfRoomsTotal: im.quartos,
      numberOfBathroomsTotal: im.suites || undefined,
      floorSize: { "@type": "QuantitativeValue", value: im.area_m2, unitCode: "MTK" },
      address: {
        "@type": "PostalAddress",
        addressLocality: im.cidade,
        addressRegion: "SP",
        addressCountry: "BR",
        ...(im.bairro ? { streetAddress: im.bairro } : {}),
      },
    },
  };
}
