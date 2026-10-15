# agent/sector_filter.py
"""
Filtro RÍGIDO de setor / empresas por perfil de busca.

Ordem de avaliação (a primeira regra que decidir encerra):
  1. Empresa na lista de EXCLUÍDAS          -> rejeita
  2. Empresa na lista de EMPRESAS-ALVO      -> aceita (independe do setor)
  3. Perfil sem setores:
       - com empresas-alvo                  -> rejeita (empresa fora da lista)
       - sem empresas-alvo                  -> aceita (sem filtro)
  4. Setor da vaga (LLM + fallback por palavras-chave) ∩ setores do perfil
       - interseção não vazia               -> aceita
       - caso contrário / setor desconhecido-> rejeita

Setores do perfil podem ser chaves da taxonomia (config/sectors.py) ou texto
livre (ex.: "naval"). Texto livre é casado contra a descrição do ramo da empresa.
"""
import re
from rapidfuzz import fuzz
from config.sectors import OTHER, keyword_sectors, normalize, resolve_sector

# Sufixos societários ignorados na comparação de nomes de empresa
_COMPANY_NOISE = re.compile(
    r"\b(ltda|s\.?a\.?|s/a|inc|corp|corporation|llc|gmbh|ag|n\.?v\.?|plc|"
    r"do brasil|brasil|brazil|group|grupo|holding|me|eireli)\b\.?"
)


def _clean_company(name: str) -> str:
    text = normalize(name)
    text = _COMPANY_NOISE.sub(" ", text)
    text = re.sub(r"[^a-z0-9& ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def company_matches(company: str, candidates: list[str]) -> str | None:
    """
    Retorna o candidato que casar com o nome da empresa, ou None.
    Casa por palavra inteira ("ford" casa "Ford Motor", mas não "Oxford")
    ou por similaridade alta de tokens ("Stellantis N.V." ~ "Stellantis").
    """
    comp = _clean_company(company)
    if not comp:
        return None
    for cand in candidates or []:
        c = _clean_company(cand)
        if not c:
            continue
        if re.search(rf"\b{re.escape(c)}\b", comp):
            return cand
        if len(comp) >= 3 and re.search(rf"\b{re.escape(comp)}\b", c):
            return cand
        # Tolerância a erros de digitação ("Stelantis" ~ "Stellantis")
        if fuzz.ratio(c, comp) >= 90:
            return cand
    return None


def job_sectors(job: dict) -> set[str]:
    """Setores (chaves da taxonomia) da empresa da vaga."""
    found: set[str] = set()
    for raw in job.get("industries") or []:
        key = resolve_sector(raw or "")
        if key:
            found.add(key)
    # Fallback por palavras-chave na descrição do ramo e no nome da empresa
    found |= keyword_sectors(job.get("industry_description") or "")
    found |= keyword_sectors(job.get("company") or "")
    found.discard(OTHER)
    return found


def is_sector_acceptable(
    job: dict,
    target_sectors: list[str] | None,
    target_companies: list[str] | None = None,
    excluded_companies: list[str] | None = None,
) -> tuple[bool, str]:
    """
    Returns:
        (aceita: bool, motivo: str)
    """
    company = job.get("company") or ""

    hit = company_matches(company, excluded_companies or [])
    if hit:
        return False, f"empresa excluida pelo usuario: '{hit}'"

    hit = company_matches(company, target_companies or [])
    if hit:
        return True, f"empresa-alvo: '{hit}'"

    if not target_sectors:
        if target_companies:
            return False, f"empresa '{company or 'desconhecida'}' fora da lista de empresas-alvo"
        return True, "perfil sem filtro de setor"

    sectors = job_sectors(job)
    wanted_keys = set()
    free_text = []
    for t in target_sectors:
        key = resolve_sector(t)
        if key:
            wanted_keys.add(key)
        elif normalize(t):
            free_text.append(normalize(t))

    common = sectors & wanted_keys
    if common:
        return True, f"setor aceito: {', '.join(sorted(common))}"

    haystack = normalize(" ".join([
        job.get("industry_description") or "",
        " ".join(job.get("industries") or []),
        company,
    ]))
    for term in free_text:
        if re.search(rf"\b{re.escape(term)}", haystack):
            return True, f"setor aceito (texto livre): '{term}'"

    detected = ", ".join(sorted(sectors)) or "desconhecido"
    return False, f"setor da empresa ({detected}) fora dos setores do perfil"
