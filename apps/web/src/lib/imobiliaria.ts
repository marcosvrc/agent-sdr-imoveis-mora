/** Dados institucionais da imobiliária, em um lugar só.
 *
 *  ⚠️ FICTÍCIOS. Este é um projeto de demonstração: não há imobiliária real por trás. Os campos
 *  marcados com `ficticio: true` (CRECI, CNPJ, endereço, telefone…) são inventados para a vitrine
 *  parecer completa; o rodapé e a página de privacidade avisam que não correspondem a uma empresa
 *  real, e eles ficam de fora do JSON-LD e de links clicáveis (`tel:`), para não virarem declaração
 *  legível por máquina nem ligação para um número de terceiro. Antes de qualquer uso real, troque
 *  pelos dados verdadeiros e use `real(...)`. `placeholder(...)` continua disponível para um campo
 *  ainda sem valor nenhum — a interface o exibe com o selo "exemplo" (components/Confianca.tsx).
 *
 *  O que NÃO está aqui, e não deve ser inventado depois: avaliações de clientes, notas, prêmios,
 *  número de imóveis vendidos, tempo de mercado. Prova social só entra com origem verificável.
 */
export type Campo = { valor: string; placeholder: boolean; ficticio?: boolean };

export const placeholder = (valor: string): Campo => ({ valor, placeholder: true });
const real = (valor: string): Campo => ({ valor, placeholder: false });
const ficticio = (valor: string): Campo => ({ valor, placeholder: false, ficticio: true });

/** Dado verdadeiro de fato: nem placeholder nem fictício. Só esse vai para JSON-LD e links. */
export const verdadeiro = (c: Campo) => !c.placeholder && !c.ficticio;

export const IMOBILIARIA = {
  nome: real("Vértice Imóveis"),
  slogan: real("O ponto de encontro entre você e o imóvel ideal."),
  assinatura: real("Vértice Imóveis — Novas perspectivas para morar e investir."),
  missao: real(
    "Conectar pessoas ao imóvel ideal por meio de um atendimento humano, inteligente e transparente, " +
    "tornando cada etapa da jornada imobiliária mais simples, segura e personalizada."
  ),
  descricao: real("Compra, venda e aluguel de imóveis em São Paulo, com atendimento imediato pela Mora."),

  // ——— fictícios: trocar pelos dados reais antes de ir ao ar ———
  creci: ficticio("CRECI-SP 48.213-J"),
  cnpj: ficticio("52.384.917/0001-60"),
  endereco: ficticio("Rua Joaquim Floriano, 820, conj. 74 — Itaim Bibi, São Paulo/SP"),
  telefone: ficticio("(11) 3456-7821"),
  telefoneLink: ficticio("+551134567821"),
  email: ficticio("contato@verticeimoveis.com.br"),
  horario: ficticio("Segunda a sexta, 9h às 18h · sábado, 9h às 13h"),
  responsavelTecnico: ficticio("Helena Arantes Duarte — CRECI-SP 127.540-F"),
} as const;

// `||` e não `??`: o compose repassa a variável mesmo quando o local/.env a deixa vazia, e um usuário
// vazio virava o link `https://t.me/` — que abre o Telegram sem conversa nenhuma.
export const TELEGRAM_USUARIO = import.meta.env.VITE_TELEGRAM_BOT_USERNAME || "mora_vertice_bot";

/** Identidade da organização para o buscador. Só entram campos preenchidos de verdade: publicar um
 *  CRECI inventado em dado estruturado seria declarar credencial falsa em formato legível por máquina. */
export const organizacaoJsonLd = () => {
  const base: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "RealEstateAgent",
    name: IMOBILIARIA.nome.valor,
    description: IMOBILIARIA.descricao.valor,
    areaServed: { "@type": "City", name: "São Paulo" },
  };
  if (verdadeiro(IMOBILIARIA.telefone)) base.telephone = IMOBILIARIA.telefone.valor;
  if (verdadeiro(IMOBILIARIA.endereco)) base.address = IMOBILIARIA.endereco.valor;
  return base;
};
