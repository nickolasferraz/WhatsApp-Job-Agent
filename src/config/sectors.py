# config/sectors.py
"""
Taxonomia de setores (ramo de atuação da EMPRESA contratante).

Fonte única de verdade usada por:
  - Front/API     -> lista de setores que o usuário pode escolher no perfil
  - query_builder -> termos curtos adicionados à busca no Google (search_terms)
  - extractor     -> chaves válidas que o Gemini deve devolver em "industries"
  - sector_filter -> fallback por palavras-chave (keywords) quando o LLM não
                     classificar o setor

Observação: o setor é da EMPRESA, não do cargo. Um Analista de TI na
Volkswagen é "automotivo"; um Motorista numa transportadora é "logistica".
"""
import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Sector:
    key: str
    label: str
    # Termos curtos para a query booleana (com acento, como aparecem nas vagas)
    search_terms: tuple[str, ...]
    # Radicais normalizados (sem acento, minúsculos) para o fallback do filtro.
    # Casados por início de palavra (ex.: "automotiv" casa "automotivo"/"automotive").
    keywords: tuple[str, ...]


OTHER = "outro"

_SECTOR_LIST: list[Sector] = [
    Sector("automotivo", "Automotivo",
           ("automotivo", "montadora", "autopeças", "automotive"),
           ("automotiv", "montadora", "autopeca", "auto peca", "veicul", "vehicle",
            "automobil", "sistemista", "fabricante de veiculos", "concessionaria")),
    Sector("logistica", "Logística e Supply Chain",
           ("logística", "supply chain", "transportadora"),
           ("logistic", "supply chain", "transportadora", "armazen", "warehouse",
            "centro de distribuicao", "frete", "freight", "3pl", "operador logistico")),
    Sector("tecnologia", "Tecnologia / TI",
           ("tecnologia", "software", "TI"),
           ("software", "tecnologia", "saas", "technology", "startup de tecnologia",
            "it services", "desenvolvimento de sistemas")),
    Sector("industria", "Indústria / Manufatura",
           ("indústria", "manufatura", "fábrica"),
           ("industria", "manufatura", "manufacturing", "fabrica", "factory",
            "fabricante", "planta industrial")),
    Sector("varejo", "Varejo e E-commerce",
           ("varejo", "e-commerce", "retail"),
           ("varejo", "retail", "e-commerce", "ecommerce", "atacad", "marketplace",
            "supermercad")),
    Sector("financeiro", "Financeiro / Bancos / Seguros",
           ("banco", "fintech", "seguradora"),
           ("bank", "banco digital", "instituicao financeira", "fintech", "seguradora",
            "insurance", "corretora de valores", "cooperativa de credito")),
    Sector("saude", "Saúde",
           ("saúde", "hospital", "healthcare"),
           ("saude", "hospital", "healthcare", "clinica", "laboratorio de analises",
            "operadora de saude")),
    Sector("energia", "Energia, Óleo e Gás",
           ("energia", "óleo e gás", "utilities"),
           ("energia", "energy", "oleo e gas", "oil and gas", "petrol", "eletric",
            "utilities", "renovave", "solar", "eolic")),
    Sector("agronegocio", "Agronegócio",
           ("agronegócio", "agro", "agribusiness"),
           ("agronegocio", "agricola", "agribusiness", "usina", "sementes",
            "fertilizante", "agropecuar")),
    Sector("alimentos", "Alimentos e Bebidas",
           ("alimentos", "bebidas", "food"),
           ("alimento", "alimenticia", "bebida", "food", "beverage", "frigorific",
            "laticinio")),
    Sector("construcao", "Construção e Engenharia",
           ("construção civil", "construtora", "engenharia"),
           ("construcao", "construtora", "construction", "incorporadora",
            "engenharia civil", "infraestrutura")),
    Sector("quimica_farma", "Química, Farmacêutica e Cosméticos",
           ("química", "farmacêutica", "pharma"),
           ("quimic", "chemical", "farmaceutic", "pharma", "cosmetic")),
    Sector("aeroespacial", "Aeroespacial e Defesa",
           ("aeroespacial", "aviação", "aerospace"),
           ("aeroespac", "aerospace", "aviacao", "aviation", "aeronave", "defesa")),
    Sector("mineracao", "Mineração e Siderurgia",
           ("mineração", "siderurgia", "mining"),
           ("mineracao", "mineradora", "mining", "siderurg", "steel", "metalurg")),
    Sector("telecom", "Telecomunicações",
           ("telecom", "telecomunicações"),
           ("telecom", "telecomunicac", "operadora de telefonia", "fibra optica")),
    Sector("educacao", "Educação",
           ("educação", "ensino", "edtech"),
           ("educacao", "educacional", "ensino", "escola", "universidade",
            "faculdade", "edtech")),
    Sector("consultoria", "Consultoria e Serviços",
           ("consultoria", "consulting"),
           ("consultoria", "consulting", "outsourcing", "servicos profissionais")),
    Sector("governo", "Setor Público",
           ("setor público", "governo", "concurso"),
           ("governo", "prefeitura", "setor publico", "autarquia", "public sector")),
]

SECTORS: dict[str, Sector] = {s.key: s for s in _SECTOR_LIST}


def normalize(text: str) -> str:
    """Minúsculas, sem acentos e com espaços colapsados."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower()).strip()


_LOOKUP: dict[str, str] = {}
for _s in _SECTOR_LIST:
    _LOOKUP[normalize(_s.key)] = _s.key
    _LOOKUP[normalize(_s.label)] = _s.key
    for _term in _s.search_terms:
        _LOOKUP.setdefault(normalize(_term), _s.key)


def resolve_sector(value: str) -> str | None:
    """
    Converte chave, rótulo ou termo ("Automotivo", "logística", "automotive")
    na chave da taxonomia. Retorna None se não reconhecer.
    """
    return _LOOKUP.get(normalize(value))


def sector_keys() -> list[str]:
    return list(SECTORS.keys())


def sectors_for_prompt() -> str:
    """Lista 'chave (Rótulo)' para injetar nos prompts do LLM."""
    lines = [f"- {s.key} ({s.label})" for s in _SECTOR_LIST]
    lines.append(f"- {OTHER} (nenhum dos anteriores)")
    return "\n".join(lines)


def keyword_sectors(text: str) -> set[str]:
    """
    Fallback: detecta setores por palavras-chave num texto curto
    (ex.: descrição do ramo da empresa devolvida pelo LLM).
    """
    norm = normalize(text)
    if not norm:
        return set()
    found = set()
    for s in _SECTOR_LIST:
        for kw in s.keywords:
            if re.search(rf"\b{re.escape(kw)}", norm):
                found.add(s.key)
                break
    return found
