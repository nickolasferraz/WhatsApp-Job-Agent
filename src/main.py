# main.py
import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron       import CronTrigger
from agent.query_builder             import BooleanQueryBuilder
from agent.search_gateway            import search_links
from agent.scraper                   import scrape_many
from agent.extractor                 import extract_title_cheap, extract_job
from agent.matcher                   import match
from agent.notifier                  import send_to_group
from agent.resume_parser             import parse_resume
from agent.seen_store                import SeenJobStore
from agent.location_filter           import is_location_acceptable
from config.settings                 import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def run_pipeline():
    log.info("Iniciando pipeline de vagas...")

    resume     = parse_resume(settings.resume_path)
    queries    = BooleanQueryBuilder().all_queries()
    seen_store = SeenJobStore()
    notified   = 0

    # =========================================================================
    # FASE 1 — Coleta: busca todas as URLs e faz scraping paralelo
    # =========================================================================
    log.info("=== FASE 1: Coleta de URLs e scraping paralelo ===")

    all_urls: list[str] = []

    for item in queries:
        site  = item["site"]
        query = item["query"]

        # Verifica se esta query ja foi executada recentemente (Redis TTL 1 dia)
        if not seen_store.is_new_query(query):
            log.info(f"  [query-skip] Query ja executada recentemente, pulando [{site}]")
            continue

        log.info(f"Buscando [{site}]: {query}")
        seen_store.mark_query(query)  # registra antes de executar

        links = search_links(query)
        log.info(f"  -> {len(links)} links encontrados")

        # Filtra URLs ja conhecidas (economiza scraping desnecessario)
        new_links = [url for url in links if seen_store.is_new_url(url)]
        skipped   = len(links) - len(new_links)
        if skipped:
            log.info(f"  -> {skipped} URL(s) ja conhecidas, ignoradas")

        all_urls.extend(new_links)

    # Remove duplicatas entre queries (mesmo link aparecendo em duas buscas)
    all_urls = list(dict.fromkeys(all_urls))
    log.info(f"Total de URLs novas para scraping: {len(all_urls)}")

    if not all_urls:
        log.info("Nenhuma URL nova encontrada. Pipeline encerrado.")
        return

    # Scraping paralelo de todas as URLs de uma vez
    scraped_pages = scrape_many(all_urls, workers=settings.scrape_workers)
    log.info(f"Scraping concluido: {len(scraped_pages)}/{len(all_urls)} paginas coletadas")

    # Registra todas as URLs scrapeadas como vistas (independente do score)
    for page in scraped_pages:
        seen_store.mark_url(page["url"])

    # =========================================================================
    # FASE 2 — Filtragem barata: dedup semantica sem custo de LLM
    # =========================================================================
    log.info("=== FASE 2: Filtragem semantica sem LLM ===")

    candidates: list[dict] = []

    for page in scraped_pages:
        title, company = extract_title_cheap(page)

        if not title:
            # Sem titulo extraivel: deixa passar para o Gemini decidir
            candidates.append(page)
            continue

        if not seen_store.is_new_job(title, company):
            log.info(f"  [dedup] Vaga ja conhecida, pulando: '{title}' @ '{company}'")
            continue

        # Guarda os dados baratos no page dict para log posterior
        page["_cheap_title"]   = title
        page["_cheap_company"] = company
        candidates.append(page)

    log.info(f"Candidatas apos filtragem barata: {len(candidates)}/{len(scraped_pages)}")

    # =========================================================================
    # FASE 3 — Processamento pago: Gemini extract + match + WhatsApp
    # =========================================================================
    log.info("=== FASE 3: Extracao Gemini + Matching + Notificacao ===")

    limit = settings.max_notifications_per_run
    for page in candidates:
        # Para ao atingir o limite de envios desta execucao
        if notified >= limit:
            log.info(f"Limite de {limit} vagas atingido. Encerrando envios.")
            break

        url = page["url"]

        # Extracao completa via Gemini
        job = extract_job(page)
        if not job:
            log.warning(f"  Falha na extracao: {url}")
            continue

        title   = job.get("title", "") or ""
        company = job.get("company", "") or ""

        # Segunda checagem semantica com dados mais precisos do Gemini
        if not seen_store.is_new_job(title, company):
            log.info(f"  [dedup-gemini] Pulando: '{title}' @ '{company}'")
            continue

        # Regra de localizacao: presencial deve estar dentro de 50km de Guarulhos
        loc_ok, loc_reason = is_location_acceptable(job)
        if not loc_ok:
            log.info(f"  [loc-filter] Rejeitada: {loc_reason} | '{title}' @ '{company}'")
            continue

        # Calculo de score
        result = match(job, resume)
        score  = result.get("score", 0)
        label  = "ACIMA" if score >= settings.min_score_to_notify else "ABAIXO"

        log.info(f"  [{label} do minimo] {title} @ {company} — {score}/100")

        if score >= settings.min_score_to_notify:
            sent = send_to_group(result)
            if sent:
                seen_store.mark_job(title, company)
                notified += 1
                log.info(f"    Enviado! ({notified}/{limit})")

    log.info(f"Pipeline concluido. {notified} vagas enviadas.")


def job():
    try:
        run_pipeline()
    except Exception as e:
        log.error(f"Erro no pipeline: {e}", exc_info=True)


if __name__ == "__main__":
    scheduler = BlockingScheduler(timezone="America/Sao_Paulo")
    scheduler.add_job(job, CronTrigger(
        day_of_week="mon-fri",
        hour="8,10,13,16",
        minute="0",))

    log.info("Agendador iniciado — rodando as 08:00 e 10:00, 13:00, 16:00 (BRT)")
    log.info("Executando pipeline inicial...")
    job()

    try:
        scheduler.start()
    except KeyboardInterrupt:
        log.info("Agendador encerrado.")