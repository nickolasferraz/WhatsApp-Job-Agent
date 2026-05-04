# agent/location_filter.py
"""
Regras de localização para filtrar vagas presenciais.

Regras:
  - Vagas REMOTAS ou HYBRID: aceitas de qualquer lugar do mundo.
  - Vagas PRESENCIAIS (on-site):
      * Aceitas APENAS em São Paulo capital e municípios muito próximos
        de Guarulhos (~40 km), conforme lista abaixo.
      * Cidades como Jundiaí, ABC Paulista (exceto Osasco), Mogi das Cruzes
        são EXPLICITAMENTE REJEITADAS por estarem distantes ou fora do
        critério do usuário, mesmo que tecnicamente <50 km.
  - Localização desconhecida (null/vazia): passa para o Gemini decidir
    pelo score — não bloqueia automaticamente.

Distâncias de referência (Guarulhos → cidade):
  Guarulhos          0 km    ✅
  São Paulo (SP)    ~20 km   ✅
  Arujá             ~20 km   ✅
  Itaquaquecetuba   ~25 km   ✅
  Mairiporã         ~25 km   ✅
  Poá               ~35 km   ✅
  Ferraz Vasconcelos~30 km   ✅
  Osasco            ~35 km   ✅ (exceção explícita do usuário)
  Barueri           ~40 km   ✅
  Carapicuíba       ~40 km   ✅
  Franco da Rocha   ~30 km   ✅
  Caieiras          ~30 km   ✅
  Cajamar           ~35 km   ✅
  Jandira           ~45 km   ✅ (limite aceitável)
  Itapevi           ~50 km   ✅ (limite)
  --------------------------------------------------------
  Santo André (ABC) ~45 km   ❌ (usuário excluiu ABC)
  São Bernardo      ~50 km   ❌ (usuário excluiu ABC)
  São Caetano       ~45 km   ❌ (usuário excluiu ABC)
  Diadema           ~45 km   ❌ (ABC)
  Mauá              ~50 km   ❌ (ABC)
  Mogi das Cruzes   ~60 km   ❌ (usuário excluiu)
  Suzano            ~50 km   ❌ (muito leste)
  Cotia             ~55 km   ❌
  Jundiaí           ~75 km   ❌ (usuário excluiu)
  Campinas          ~90 km   ❌
"""
import logging
import re

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LISTA DE REJEIÇÃO EXPLÍCITA (tem prioridade sobre a lista de aceitos)
# Cidades que o usuário quer excluir, mesmo que "próximas"
# ---------------------------------------------------------------------------
_EXPLICITLY_REJECTED = {
    # ABC Paulista (exceto Osasco, que é aceita)
    "santo andre", "santo andré",
    "sao bernardo", "são bernardo",
    "sao bernardo do campo", "são bernardo do campo",
    "sao caetano", "são caetano",
    "sao caetano do sul", "são caetano do sul",
    "diadema",
    "maua", "mauá",
    "ribeirao pires", "ribeirão pires",
    "rio grande da serra",
    # Mogi das Cruzes e região
    "mogi das cruzes",
    "biritiba mirim",
    "suzano",
    # Jundiaí e região
    "jundiai", "jundiaí",
    "campo limpo paulista",
    "valinhos",
    "vinhedo",
    "itatiba",
    # Outras cidades distantes
    "cotia",
    "embu das artes",
    "embu-guacu", "embu guacu",
    "itapecerica da serra",
    "sao lourenco da serra", "são lourenço da serra",
    "taboao da serra", "taboão da serra",
    # Campinas e interior
    "campinas",
    "sorocaba",
    "santos",
    "sao jose dos campos", "são josé dos campos",
    "ribeirao preto", "ribeirão preto",
}

# ---------------------------------------------------------------------------
# LISTA DE CIDADES ACEITAS (presencial ok)
# São Paulo capital + municípios muito próximos de Guarulhos
# ---------------------------------------------------------------------------
_CITIES_ACCEPTED = {
    # SP capital e Guarulhos
    "sao paulo", "são paulo", "sp",
    "guarulhos",
    # Municípios próximos (zona norte/leste)
    "aruja", "arujá",
    "santa isabel",
    "mairipora", "mairiporã",
    "itaquaquecetuba",
    "poa", "poá",
    "ferraz de vasconcelos",
    "franco da rocha",
    "francisco morato",
    "caieiras",
    "cajamar",
    "pirapora do bom jesus",
    # Zona oeste (Osasco é exceção explícita do usuário)
    "osasco",
    "carapicuiba", "carapicuíba",
    "barueri",
    "santana de parnaiba", "santana de parnaíba",
    "jandira",
    "itapevi",
    # Genérico aceitável
    "grande sao paulo", "grande são paulo",
    "regiao metropolitana de sao paulo",
    "região metropolitana de são paulo",
    "rmsp",
    "latam",
}

# Padrões que indicam modalidade remota no próprio campo location
_REMOTE_PATTERNS = re.compile(
    r"\b(remot|remote|home.?office|homeoffice|hibrido|hybrid|hibrida)\b",
    re.IGNORECASE,
)


def _normalize(text: str) -> str:
    """Lowercase e remove acentos básicos para comparação."""
    text = text.lower().strip()
    for src, dst in [
        ("ã", "a"), ("â", "a"), ("á", "a"), ("à", "a"),
        ("ê", "e"), ("é", "e"), ("è", "e"),
        ("î", "i"), ("í", "i"),
        ("ô", "o"), ("ó", "o"), ("õ", "o"),
        ("û", "u"), ("ú", "u"),
        ("ç", "c"),
    ]:
        text = text.replace(src, dst)
    return text


def is_location_acceptable(job: dict) -> tuple[bool, str]:
    """
    Verifica se a localização da vaga atende às regras de distância.

    Returns:
        (aceita: bool, motivo: str)
    """
    work_mode = _normalize(job.get("work_mode") or "")
    location  = _normalize(job.get("location") or "")

    # Remota ou híbrida → sempre aceita
    if "remote" in work_mode or "hybrid" in work_mode or "hibrido" in work_mode:
        return True, "remota/hibrida - aceita"

    # Localização vazia → deixa o score decidir
    if not location:
        return True, "localizacao desconhecida - passa para score"

    # Verifica se o location tem indicação de remoto no próprio texto
    if _REMOTE_PATTERNS.search(location):
        return True, "location indica remoto"

    loc_norm = _normalize(location)

    # Rejeição explícita tem PRIORIDADE sobre a lista de aceitos
    for rejected_city in _EXPLICITLY_REJECTED:
        if rejected_city in loc_norm:
            return False, f"cidade explicitamente rejeitada: '{rejected_city}' em '{location}'"

    # Verifica se está na lista de cidades aceitas
    for city in _CITIES_ACCEPTED:
        if city in loc_norm:
            return True, f"presencial aceita: '{city}'"

    # Não encontrada em nenhuma lista → rejeita (política conservadora)
    return False, f"cidade fora da area aceita: '{location}' | modo: '{work_mode or 'nao informado'}'"
