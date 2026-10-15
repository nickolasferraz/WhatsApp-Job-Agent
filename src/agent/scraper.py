# agent/scraper.py
import sys
import logging
import hashlib
import httpx
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

log = logging.getLogger(__name__)


def _is_static_site(domain: str) -> bool:
    """
    Retorna True se o domínio deve ser scrapeado via httpx (sem Playwright).
    A lista e controlada em settings.static_sites — fonte unica de verdade.
    """
    from config.settings import settings
    return any(s in domain for s in settings.static_sites)


def _headers():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124",
        "Accept-Language": "pt-BR,pt;q=0.9"
    }


def scrape_static(url: str) -> dict:
    resp = httpx.get(url, headers=_headers(), timeout=15, follow_redirects=True)
    soup = BeautifulSoup(resp.text, "lxml")
    return {
        "url":  url,
        "id":   hashlib.md5(url.encode()).hexdigest(),
        "html": resp.text,
        "text": soup.get_text(separator="\n", strip=True),
    }


def scrape_dynamic(url: str) -> dict:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_extra_http_headers(_headers())
        page.goto(url, wait_until="networkidle", timeout=30000)
        html = page.content()
        text = page.inner_text("body")
        browser.close()
    return {
        "url":  url,
        "id":   hashlib.md5(url.encode()).hexdigest(),
        "html": html,
        "text": text,
    }


def scrape_page(url: str) -> dict:
    """Scraping de uma unica URL (compatibilidade com codigo anterior)."""
    domain = urlparse(url).netloc
    if _is_static_site(domain):
        return scrape_static(url)
    return scrape_dynamic(url)


def _scrape_one(url: str) -> dict | None:
    """Wrapper com tratamento de erro para uso no pool paralelo."""
    try:
        result = scrape_page(url)
        log.info(f"  [scrape] OK -> {url}")
        return result
    except Exception as e:
        log.warning(f"  [scrape] ERRO em {url}: {type(e).__name__}: {e}")
        return None


def scrape_many(urls: list[str], workers: int = 4) -> list[dict]:
    """
    Faz scraping de varias URLs em paralelo usando ThreadPoolExecutor.

    Args:
        urls:    lista de URLs a serem scrapeadas
        workers: numero de threads simultaneas (default 4)
                 - mais workers = mais rapido, mas mais RAM e risco de bloqueio
                 - LinkedIn bloqueia facilmente com muitos workers; 4 e seguro

    Returns:
        Lista de dicts {url, id, html, text} — apenas as bem-sucedidas.
        A ordem pode diferir da entrada (quem terminar primeiro entra primeiro).
    """
    if not urls:
        return []

    log.info(f"[scrape_many] Iniciando scraping paralelo: {len(urls)} URLs, {workers} workers")
    results = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_scrape_one, url): url for url in urls}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                results.append(result)

    log.info(f"[scrape_many] Concluido: {len(results)}/{len(urls)} paginas coletadas")
    return results

# Adicionado
def scrape_github_remote_in_tech() -> list[dict]:
    """
    Varre o repositório remoteintech/remote-jobs via API do GitHub.
    Usa settings.github_remote_in_tech_api.
    Retorna lista de dicts {name, url, job_listings}.
    Filtra empresas com 'Worldwide' ou 'Brazil' na região.
    Usa httpx (scraping estático) — sem Playwright.
    """
    from config.settings import settings
    log.info("[scrape_github_remote_in_tech] Iniciando busca no repo remoteintech")
    results = []
    try:
        resp = httpx.get(settings.github_remote_in_tech_api, headers=_headers(), timeout=15)
        resp.raise_for_status()
        files = resp.json()
        
        for file in files:
            if file.get("type") == "file" and file.get("name", "").endswith(".md"):
                file_url = file.get("download_url")
                if file_url:
                    # Coleta o conteudo markdown
                    file_resp = httpx.get(file_url, headers=_headers(), timeout=15)
                    if file_resp.status_code == 200:
                        content = file_resp.text
                        if "Worldwide" in content or "Brazil" in content:
                            results.append({
                                "name": file.get("name").replace(".md", ""),
                                "url": file.get("html_url"),
                                "job_listings": content
                            })
        log.info(f"  [scrape_github_remote_in_tech] Encontradas {len(results)} empresas relevantes")
    except Exception as e:
        log.error(f"Erro em scrape_github_remote_in_tech: {e}")
    return results

# Adicionado
def scrape_hacker_news_hiring(stack: str) -> list[dict]:
    """
    Acessa o thread 'Who is hiring' mais recente no Hacker News.
    Filtra comentários que mencionam a stack do usuário.
    Retorna lista de dicts {text, url, author}.
    Usa httpx (scraping estático).
    """
    log.info(f"[scrape_hacker_news_hiring] Buscando vagas para stack: {stack}")
    results = []
    try:
        # Pega a busca do HN via algolia
        search_url = "https://hn.algolia.com/api/v1/search_by_date?query=who+is+hiring&tags=story,author_whoishiring"
        resp = httpx.get(search_url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        if not data.get("hits"):
            return results
            
        latest_thread = data["hits"][0]
        thread_id = latest_thread["objectID"]
        
        # Pega o HTML do thread
        thread_url = f"https://news.ycombinator.com/item?id={thread_id}"
        html_resp = httpx.get(thread_url, headers=_headers(), timeout=15)
        html_resp.raise_for_status()
        
        soup = BeautifulSoup(html_resp.text, "lxml")
        comments = soup.find_all("tr", class_="athing comtr")
        
        for comment in comments:
            text_elem = comment.find("div", class_="commtext")
            if text_elem:
                text = text_elem.get_text(separator="\n", strip=True)
                if stack.lower() in text.lower():
                    user_elem = comment.find("a", class_="hnuser")
                    author = user_elem.text if user_elem else "unknown"
                    
                    results.append({
                        "text": text,
                        "url": f"https://news.ycombinator.com/item?id={comment.get('id')}",
                        "author": author
                    })
        log.info(f"  [scrape_hacker_news_hiring] Encontrados {len(results)} comentários relevantes")
    except Exception as e:
        log.warning(f"  [scrape_hacker_news_hiring] Erro: {e}")
    return results