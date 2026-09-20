import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Botao, CabecalhoPagina, Campo, Card, Erro, cx, entradaCls, foco } from "../componentes/ui";
import { Ic } from "../componentes/Icones";
import { api, type FotoImovel, type ImovelNovo } from "../lib/api";

/** Cadastro de imóvel — ação humana (`exigir_humano` na API).
 *
 *  O agente lê o catálogo e não o escreve: imóvel cadastrado a partir de uma conversa seria o
 *  caminho mais curto para um anúncio inventado. Esta tela é o outro lado dessa regra — sem ela,
 *  a única forma de ter acervo era rodar o seed.
 *
 *  **Custos separados, e vazio é DESCONHECIDO.** Condomínio e IPTU em branco não viram zero: o
 *  banco guarda nulo e a vitrine mostra "total incompleto" em vez de um número menor do que a
 *  conta real. Zero digitado é outra coisa — é alguém afirmando que não há condomínio.
 */
export function NovoImovel() {
  const ir = useNavigate();
  const qc = useQueryClient();
  const [f, setF] = useState({
    code: "", title: "", description: "", city: "São Paulo", neighborhood: "",
    type: "apartamento", purpose: "rent", status: "available",
    preco: "", condominio: "", iptu: "", outros: "", bedrooms: "0", parking: "0", area: "",
  });
  const [fotos, setFotos] = useState<FotoImovel[]>([]);
  const set = (k: keyof typeof f, v: string) => setF((x) => ({ ...x, [k]: v }));

  // Reais digitados → centavos. A conversão mora num lugar só; espalhá-la é como um valor sai
  // cem vezes maior numa tela e certo em todas as outras.
  const centavos = (v: string): number | null => {
    const limpo = v.replace(/\s/g, "").replace(/\./g, "").replace(",", ".");
    if (limpo === "") return null;
    const n = Number(limpo);
    return Number.isFinite(n) && n >= 0 ? Math.round(n * 100) : null;
  };

  const aluguel = f.purpose === "rent";
  const precoOk = centavos(f.preco) !== null && (centavos(f.preco) ?? 0) > 0;
  const podeSalvar = f.code.trim() && f.title.trim() && f.neighborhood.trim() && precoOk;

  const salvar = useMutation({
    mutationFn: () => {
      const corpo: ImovelNovo = {
        code: f.code.trim(), title: f.title.trim(),
        description: f.description.trim() || null,
        city: f.city.trim(), neighborhood: f.neighborhood.trim(),
        type: f.type, purpose: f.purpose as "rent" | "buy",
        base_price_cents: centavos(f.preco)!,
        // Só aluguel tem custo mensal. Em compra, mandar zero seria afirmar que não há — e não é
        // disso que se trata: não se aplica.
        condo_monthly_cents: aluguel ? centavos(f.condominio) : null,
        property_tax_monthly_cents: aluguel ? centavos(f.iptu) : null,
        other_monthly_cents: aluguel ? centavos(f.outros) : null,
        bedrooms: Number(f.bedrooms) || 0, parking: Number(f.parking) || 0,
        area_m2: f.area ? Number(f.area.replace(",", ".")) : null,
        status: f.status,
        photos: fotos.filter((x) => x.url.trim()),
      };
      return api.criarImovel(corpo);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["imoveis"] });
      ir("/imoveis");
    },
  });

  return (
    <form onSubmit={(e) => { e.preventDefault(); if (podeSalvar) salvar.mutate(); }}>
      <CabecalhoPagina titulo="Novo imóvel" voltar={{ para: "/imoveis", r: "Imóveis" }}
        descricao="Cadastro é ação humana. O agente lê o catálogo e nunca escreve nele."
        acoes={<Botao variante="primario" type="submit" ocupado={salvar.isPending} disabled={!podeSalvar}>
                 Cadastrar imóvel
               </Botao>} />

      {salvar.error ? <div className="mb-4"><Erro erro={salvar.error} /></div> : null}

      <div className="grid items-start gap-4 lg:grid-cols-2">
        <Card titulo="Identificação">
          <div className="grid gap-3 sm:grid-cols-2">
            <Campo rotulo="Código" dica="A chave entre o CRM e a Mora — é por ele que ela pede horários deste imóvel.">
              <input className={entradaCls} value={f.code} onChange={(e) => set("code", e.target.value.toUpperCase())}
                     placeholder="SP-0201" required />
            </Campo>
            <Campo rotulo="Situação">
              <select className={entradaCls} value={f.status} onChange={(e) => set("status", e.target.value)}>
                <option value="available">Disponível</option>
                <option value="reserved">Reservado</option>
                <option value="unavailable">Indisponível</option>
              </select>
            </Campo>
            <div className="sm:col-span-2">
              <Campo rotulo="Título">
                <input className={entradaCls} value={f.title} onChange={(e) => set("title", e.target.value)}
                       placeholder="Apartamento em Pinheiros" required />
              </Campo>
            </div>
            <Campo rotulo="Cidade">
              <input className={entradaCls} value={f.city} onChange={(e) => set("city", e.target.value)} required />
            </Campo>
            <Campo rotulo="Bairro" dica="A Mora deduz a região a partir daqui.">
              <input className={entradaCls} value={f.neighborhood} onChange={(e) => set("neighborhood", e.target.value)} required />
            </Campo>
            <Campo rotulo="Tipo">
              <select className={entradaCls} value={f.type} onChange={(e) => set("type", e.target.value)}>
                {["apartamento", "casa", "studio", "cobertura", "sobrado", "kitnet"].map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </Campo>
            <Campo rotulo="Finalidade">
              <select className={entradaCls} value={f.purpose} onChange={(e) => set("purpose", e.target.value)}>
                <option value="rent">Aluguel</option>
                <option value="buy">Compra</option>
              </select>
            </Campo>
            <div className="sm:col-span-2">
              <Campo rotulo="Descrição" dica="O que a Mora vai ler para descrever o imóvel na conversa.">
                <textarea className={cx(entradaCls, "min-h-[72px]")} value={f.description}
                          onChange={(e) => set("description", e.target.value)} />
              </Campo>
            </div>
          </div>
        </Card>

        <div className="space-y-4">
          <Card titulo="Valores e medidas">
            <div className="grid gap-3 sm:grid-cols-2">
              <Campo rotulo={aluguel ? "Aluguel (R$)" : "Preço (R$)"}>
                <input className={entradaCls} inputMode="decimal" value={f.preco}
                       onChange={(e) => set("preco", e.target.value)} placeholder="3.500" required />
              </Campo>
              <Campo rotulo="Área (m²)">
                <input className={entradaCls} inputMode="decimal" value={f.area}
                       onChange={(e) => set("area", e.target.value)} placeholder="70" />
              </Campo>
              {aluguel && (
                <>
                  <Campo rotulo="Condomínio (R$)" dica="Em branco = desconhecido. Zero = afirma que não há.">
                    <input className={entradaCls} inputMode="decimal" value={f.condominio}
                           onChange={(e) => set("condominio", e.target.value)} />
                  </Campo>
                  <Campo rotulo="IPTU mensal (R$)" dica="Em branco = desconhecido.">
                    <input className={entradaCls} inputMode="decimal" value={f.iptu}
                           onChange={(e) => set("iptu", e.target.value)} />
                  </Campo>
                  <Campo rotulo="Outros custos (R$)">
                    <input className={entradaCls} inputMode="decimal" value={f.outros}
                           onChange={(e) => set("outros", e.target.value)} />
                  </Campo>
                </>
              )}
              <Campo rotulo="Quartos">
                <input className={entradaCls} type="number" min={0} max={30} value={f.bedrooms}
                       onChange={(e) => set("bedrooms", e.target.value)} />
              </Campo>
              <Campo rotulo="Vagas">
                <input className={entradaCls} type="number" min={0} max={30} value={f.parking}
                       onChange={(e) => set("parking", e.target.value)} />
              </Campo>
            </div>
            {aluguel && (
              <p className="mt-3 border-t border-line pt-3 text-[11px] text-inkMuted">
                Custo deixado em branco vira <b>desconhecido</b>, não zero: o total mensal sai marcado
                como incompleto em vez de sair menor do que a conta real. É o que evita a surpresa do
                cliente no dia da assinatura.
              </p>
            )}
          </Card>

          <Fotos fotos={fotos} aoMudar={setFotos} />
        </div>
      </div>
    </form>
  );
}

/** Galeria por URL.
 *
 *  A foto é uma referência, e o binário não mora no banco: o CRM divide o Postgres com o agente, e
 *  imagem gravada em coluna ocupa conexão do pool que deveria estar atendendo conversa — além de
 *  entrar em todo backup. Colar a URL resolve o cadastro hoje e não muda nada quando o envio de
 *  arquivo entrar: a coluna já é a referência, só passa a ser preenchida por um upload.
 */
function Fotos({ fotos, aoMudar }: { fotos: FotoImovel[]; aoMudar: (f: FotoImovel[]) => void }) {
  const mover = (i: number, passo: number) => {
    const j = i + passo;
    if (j < 0 || j >= fotos.length) return;
    const copia = [...fotos];
    [copia[i], copia[j]] = [copia[j], copia[i]];
    aoMudar(copia);
  };

  return (
    <Card titulo="Fotos" acoes={
      <Botao type="button" onClick={() => aoMudar([...fotos, { url: "", alt: "" }])}>+ Adicionar</Botao>
    }>
      {fotos.length === 0 ? (
        <p className="text-xs text-inkMuted">
          Sem foto, o imóvel aparece na vitrine com o espaço vazio — e não com uma imagem genérica,
          que o cliente leria como sendo este imóvel.
        </p>
      ) : (
        <ul className="space-y-3">
          {fotos.map((foto, i) => (
            <li key={i} className="rounded-lg border border-line p-2.5">
              <div className="mb-1.5 flex items-center justify-between gap-2">
                <span className="text-[11px] font-medium text-inkMuted">
                  {i === 0 ? "Capa — vai para o cartão e para a busca" : `Foto ${i + 1}`}
                </span>
                <span className="flex items-center gap-1">
                  <button type="button" onClick={() => mover(i, -1)} disabled={i === 0}
                          aria-label={`Mover a foto ${i + 1} para cima`}
                          className={cx("rounded p-1 text-inkMuted hover:bg-surface2 disabled:opacity-30", foco)}>
                    <Ic.subindo size={14} />
                  </button>
                  <button type="button" onClick={() => mover(i, 1)} disabled={i === fotos.length - 1}
                          aria-label={`Mover a foto ${i + 1} para baixo`}
                          className={cx("rounded p-1 text-inkMuted hover:bg-surface2 disabled:opacity-30", foco)}>
                    <Ic.descendo size={14} />
                  </button>
                  <button type="button" onClick={() => aoMudar(fotos.filter((_, k) => k !== i))}
                          aria-label={`Remover a foto ${i + 1}`}
                          className={cx("rounded p-1 text-ruim hover:bg-ruimSoft", foco)}>
                    <Ic.limpar size={14} />
                  </button>
                </span>
              </div>
              <div className="grid gap-2 sm:grid-cols-[1.4fr_1fr]">
                <input className={entradaCls} value={foto.url} placeholder="https://…"
                       aria-label={`Endereço da foto ${i + 1}`}
                       onChange={(e) => aoMudar(fotos.map((x, k) => k === i ? { ...x, url: e.target.value } : x))} />
                <input className={entradaCls} value={foto.alt ?? ""} placeholder="descrição (opcional)"
                       aria-label={`Descrição da foto ${i + 1}`}
                       onChange={(e) => aoMudar(fotos.map((x, k) => k === i ? { ...x, alt: e.target.value } : x))} />
              </div>
              {foto.url && !/^https?:\/\//.test(foto.url) && (
                /* A mesma regra do servidor, dita antes de o botão falhar: o que entra aqui vira
                   `<img src>` na vitrine e dado estruturado da ficha. */
                <p className="mt-1 text-[11px] text-ruim">Precisa começar com http:// ou https://</p>
              )}
            </li>
          ))}
          <li className="text-[11px] text-inkFaint">
            O endereço precisa ser público e estável — link que expira quebra os dados estruturados da
            ficha dias depois, quando ninguém está olhando.
          </li>
        </ul>
      )}
    </Card>
  );
}
