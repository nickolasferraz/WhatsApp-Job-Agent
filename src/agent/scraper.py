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