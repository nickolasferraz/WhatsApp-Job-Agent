# agent/search_gateway.py
import re
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from serpapi import GoogleSearch
from config.settings import settings

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Padrões de URL direta por site (vaga individual, pronta para candidatura)
# ---------------------------------------------------------------------------

# LinkedIn: URL direta tem /jobs/view/<ID_NUMERICO>/
_LINKEDIN_DIRECT = re.compile(r"/jobs/view/\d+", re.IGNORECASE)

# Gupy: URL direta é do subdomínio da empresa com /jobs/<ID>
# Ex: empresa.gupy.io/jobs/1234567
_GUPY_DIRECT = re.compile(r"\.gupy\.io/jobs/\d+", re.IGNORECASE)

# Catho: URL direta tem /<ID_NUMERICO>/ no final do path
# Ex: catho.com.br/vagas/analista/35702999/
_CATHO_DIRECT = re.compile(r"/vagas/.+/\d+/?$", re.IGNORECASE)

# InfoJobs e Vagas.com: qualquer URL com segmento numérico de ID no path
_GENERIC_DIRECT = re.compile(r"/\d{5,}/", re.IGNORECASE)

# Adicionado
# Lever: jobs.lever.co/empresa/uuid-da-vaga
_LEVER_DIRECT = re.compile(r"/jobs/[a-f0-9\-]{8,}", re.IGNORECASE)

# Indeed: indeed.com/viewjob?jk=abc123
_INDEED_DIRECT = re.compile(r"(viewjob|/rc/clk)\?.*jk=", re.IGNORECASE)

# Wellfound: wellfound.com/jobs/123456
_WELLFOUND_DIRECT = re.compile(r"/jobs/\d+", re.IGNORECASE)

# Remote OK: remoteok.com/remote-jobs/java-developer-empresa-123
_REMOTEOK_DIRECT = re.compile(r"/remote-jobs/[a-z0-9\-]+-\d+", re.IGNORECASE)

# We Work Remotely: weworkremotely.com/remote-jobs/12345-titulo
_WWR_DIRECT = re.compile(r"/remote-jobs/\d+-", re.IGNORECASE)

# Big Techs: padrão genérico por path com ID ou slug
_BIGTECH_DIRECT = re.compile(r"/(jobs|positions|careers|openings)/[\w\-]+/?\d*/?$", re.IGNORECASE)

# Glassdoor: glassdoor.com/job-listing/titulo-JVID12345.htm
_GLASSDOOR_DIRECT = re.compile(r"/job-listing/.*JVID\d+", re.IGNORECASE)

# Hacker News: item individual
_HN_DIRECT = re.compile(r"/item\?id=\d+", re.IGNORECASE)


def is_direct_job_url(url: str) -> bool:
    """
    Retorna True se a URL aponta para uma vaga individual (pagina de candidatura).
    Retorna False se for uma pagina de listagem/busca.

    Exemplos rejeitados (listagem):
      linkedin.com/jobs/estagiario-supply-chain-vagas
      br.linkedin.com/jobs/estagios-logistica-vagas-sao-paulo
      portal.gupy.io/job-search/term=Auxiliar

    Exemplos aceitos (vaga direta):
      linkedin.com/jobs/view/3987654321/
      empresa.gupy.io/jobs/11185976
      catho.com.br/vagas/analista-de-logistica/35702999/
    """
    url_lower = url.lower()

    # LinkedIn
    if "linkedin.com" in url_lower:
        return bool(_LINKEDIN_DIRECT.search(url))

    # Gupy
    if "gupy.io" in url_lower:
        # portal.gupy.io é página de busca — rejeita
        if "portal.gupy.io" in url_lower:
            return False
        return bool(_GUPY_DIRECT.search(url))

    # Catho
    if "catho.com.br" in url_lower:
        return bool(_CATHO_DIRECT.search(url))

    # Adicionado
    if "lever.co" in url_lower:
        return bool(_LEVER_DIRECT.search(url))
    if "indeed.com" in url_lower:
        return bool(_INDEED_DIRECT.search(url))
    if "wellfound.com" in url_lower:
        return bool(_WELLFOUND_DIRECT.search(url))
    if "remoteok.com" in url_lower:
        return bool(_REMOTEOK_DIRECT.search(url))
    if "weworkremotely.com" in url_lower:
        return bool(_WWR_DIRECT.search(url))
    if any(bt in url_lower for bt in ["careers.google.com", "metacareers.com", "jobs.apple.com", "amazon.jobs", "careers.microsoft.com", "jobs.netflix.com", "lifeatspotify.com", "uber.com/careers"]):
        return bool(_BIGTECH_DIRECT.search(url))
    if "glassdoor.com" in url_lower:
        return bool(_GLASSDOOR_DIRECT.search(url))
    if "news.ycombinator.com" in url_lower:
        return bool(_HN_DIRECT.search(url))

    # InfoJobs / Vagas.com / outros: aceita se houver ID numérico no path
    if "infojobs.com.br" in url_lower or "vagas.com.br" in url_lower:
        return bool(_GENERIC_DIRECT.search(url))

    # Sites desconhecidos: aceita por padrão (não bloqueia)
    return True


def search_links(query: str) -> list[str]:
    """
    Executa a busca na SerpAPI e retorna apenas URLs de vagas diretas,
    filtrando paginas de listagem que nao levam ao formulario de candidatura.
    """
    search = GoogleSearch({
        "q":       query,
        "num":     settings.max_results_per_query,
        "api_key": settings.serpapi_key,
        "hl":      "pt-br",
        "gl":      "br",
        "tbs":     "qdr:w", # Limita aos resultados dos ultimos 7 dias (qdr:d para 24h)
    })

    results   = search.get_dict()
    all_links = [r["link"] for r in results.get("organic_results", [])]

    direct = [url for url in all_links if is_direct_job_url(url)]
    skipped = len(all_links) - len(direct)

    if skipped:
        log.info(f"  [gateway] {skipped} URL(s) de listagem descartadas, {len(direct)} diretas mantidas")

    return direct

# Adicionado
def build_boolean_queries(stack: str, framework: str) -> list[str]:
    """
    Substitui os placeholders {stack} e {framework} nos templates de
    settings.boolean_search_queries e retorna a lista pronta para SerpAPI.
    """
    queries = []
    for q in settings.boolean_search_queries:
        queries.append(q.format(stack=stack, framework=framework))
    return queries