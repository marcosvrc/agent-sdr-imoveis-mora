from pydantic import BaseModel


class Imovel(BaseModel):
    id: str
    tipo: str
    operacao: str            # venda | aluguel
    cidade: str
    regiao: str              # zona_sul, zona_oeste...
    bairro: str
    quartos: int
    suites: int = 0
    vagas: int = 0
    area_m2: float
    preco: float
    condominio: float | None = None
    descricao: str
    fotos: list[str] = []
    destaque_investimento: bool = False

    def fotos_absolutas(self, base: str) -> list[str]:
        """Fotos enviadas pelo painel ficam gravadas como caminho relativo (/fotos/...); aqui viram URL completa."""
        base = base.rstrip("/")
        return [f"{base}{f}" if f.startswith("/") else f for f in self.fotos]

    def texto_canonico(self) -> str:
        """Texto que vai para o embedding — um chunk por imóvel (ADR-0001).

        Inclui apelidos e pontos de referência do bairro (sdr_shared.geo) para que a parte semântica do
        RAG case com o jeito que o cliente fala ("perto da Faria Lima", "do lado do Ibirapuera").
        """
        from ..geo import BAIRROS
        info = BAIRROS.get(self.bairro, {})
        vizinhanca = ", ".join([*info.get("apelidos", []), *info.get("refs", [])])
        perto = f" Perto de: {vizinhanca}." if vizinhanca else ""
        return (
            f"{self.tipo.capitalize()} para {self.operacao} em {self.bairro}, {self.regiao.replace('_', ' ')} "
            f"de {self.cidade}. {self.quartos} quartos ({self.suites} suíte), {self.area_m2:.0f} m², "
            f"{self.vagas} vaga(s). {self.descricao}{perto} Preço: R$ {self.preco:,.0f}."
        )

    def metadata(self) -> dict:
        """Metadados para filtro na Knowledge Base (arquivo .metadata.json)."""
        return {"metadataAttributes": {
            "tipo": self.tipo, "operacao": self.operacao, "regiao": self.regiao,
            "bairro": self.bairro, "quartos": self.quartos, "preco": self.preco, "area_m2": self.area_m2,
            "cidade": self.cidade,
        }}


class ImovelCard(BaseModel):
    """Forma neutra que o agente devolve; o canal renderiza (card WhatsApp, componente React)."""
    id: str
    titulo: str
    preco: float
    foto: str | None = None
    motivo: str              # por que combina com o lead
