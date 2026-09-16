/** Dados institucionais da imobiliária, em um lugar só.
 *
 *  ⚠️ PLACEHOLDERS. Este é um projeto de demonstração: não há imobiliária real por trás, e inventar
 *  CRECI, endereço, telefone ou depoimento seria fabricar credencial — o oposto do que uma página
 *  de confiança deve fazer. Todo campo abaixo marcado com `placeholder: true` precisa ser trocado
 *  pelo dado verdadeiro antes de qualquer uso real; enquanto não for, a interface o exibe com aviso
 *  visível (ver `SeloPlaceholder` em components/Confianca.tsx) em vez de fingir que é verdade.
 *
 *  O que NÃO está aqui, e não deve ser inventado depois: avaliações de clientes, notas, prêmios,
 *  número de imóveis vendidos, tempo de mercado. Prova social só entra com origem verificável.
 */
export type Campo = { valor: string; placeholder: boolean };

const ph = (valor: string): Campo => ({ valor, placeholder: true });
const real = (valor: string): Campo => ({ valor, placeholder: false });

export const IMOBILIARIA = {
  nome: real("Vértice Imóveis"),
  slogan: real("O ponto de encontro entre você e o imóvel ideal."),
  assinatura: real("Vértice Imóveis — Novas perspectivas para morar e investir."),
  missao: real(
    "Conectar pessoas ao imóvel ideal por meio de um atendimento humano, inteligente e transparente, " +
    "tornando cada etapa da jornada imobiliária mais simples, segura e personalizada."
  ),
  descricao: real("Compra, venda e aluguel de imóveis em São Paulo, com atendimento imediato pela Mora."),

  // ——— trocar antes de ir ao ar ———
  creci: ph("CRECI-SP 00000-J"),
  cnpj: ph("00.000.000/0001-00"),
  endereco: ph("Av. Exemplo, 1000 — Itaim Bibi, São Paulo/SP"),
  telefone: ph("(11) 0000-0000"),
  telefoneLink: ph("+551100000000"),
  email: ph("contato@exemplo.com.br"),
  horario: ph("Segunda a sexta, 9h às 18h · sábado, 9h às 13h"),
  responsavelTecnico: ph("Nome do corretor responsável — CRECI-SP 00000-F"),
} as const;

export const TELEGRAM_USUARIO = import.meta.env.VITE_TELEGRAM_BOT_USERNAME ?? "mora_vertice_bot";

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
  if (!IMOBILIARIA.telefone.placeholder) base.telephone = IMOBILIARIA.telefone.valor;
  if (!IMOBILIARIA.endereco.placeholder) base.address = IMOBILIARIA.endereco.valor;
  return base;
};
