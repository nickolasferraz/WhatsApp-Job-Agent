# main.py
import logging
import os
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron       import CronTrigger
from agent.query_builder             import BooleanQueryBuilder
from agent.search_gateway            import search_links
from agent.scraper                   import scrape_many
from agent.extractor                 import extract_title_cheap, extract_job
from agent.matcher                   import match
from agent.notifier                  import send_to_target
from agent.resume_parser             import parse_resume
from agent.seen_store                import SeenJobStore
from agent.location_filter           import is_location_acceptable
from agent.sector_filter             import is_sector_acceptable
from config.settings                 import settings
from config.database                 import SessionLocal
from models.job                      import User, Resume

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def migrate_legacy_user_if_needed(db, user: User) -> list[Resume]:
    """
    Migra automaticamente usuários criados na versão antiga
    (que guardavam o PDF em user.resume) para a nova tabela 'resumes'.
    """
    if not user.resumes and user.resume:
        log.info(f"Migrando currículo legado para perfil de busca do usuário {user.name}...")
        legacy_resume = Resume(
            user_id=user.id,
            label="Currículo Principal",
            filename="curriculo.pdf",
            resume_pdf=user.resume,
            keyword_roles=user.keyword_roles or [],
            keyword_locations=user.keyword_locations or [],
            keyword_levels=user.keyword_levels or [],
            target_sectors=[],
            target_companies=[],
            excluded_companies=[],
            is_active=True,
        )
        db.add(legacy_resume)
        db.commit()
        db.refresh(user)

    return [r for r in user.resumes if r.is_active]


def run_pipeline():
    log.info("Iniciando pipeline global de vagas...")
    db = SessionLocal()
    try:
        users = db.query(User).all()
        if not users:
            log.info("Nenhum usuário encontrado no banco de dados. Encerrando.")
            return

        for user in users:
            try:
                run_pipeline_for_user(user, db)
            except Exception as e:
                log.error(f"Erro ao processar usuário {user.name} (id={user.id}): {e}", exc_info=True)
    finally:
        db.close()


def run_pipeline_for_user_by_id(user_id):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            run_pipeline_for_user(user, db)
    finally:
        db.close()


def run_pipeline_for_user(user: User, db=None):
    close_db_at_end = False
    if db is None:
        db = SessionLocal()
        close_db_at_end = True

    try:
        log.info(f"\n{'='*55}\n=== Pipeline para usuário: {user.name} ({user.email}) ===\n{'='*55}")

        active_resumes = migrate_legacy_user_if_needed(db, user)

        if not active_resumes:
            log.warning(f"Usuário {user.name} não possui nenhum currículo/perfil ativo. Pulando.")
            return

        if not user.phone:
            log.warning(f"Usuário {user.name} não possui telefone cadastrado para WhatsApp. Pulando.")
            return

        seen_store = SeenJobStore()

        for resume_profile in active_resumes:
            try:
                run_pipeline_for_resume(user, resume_profile, seen_store, db)
            except Exception as e:
                log.error(f"Erro no perfil '{resume_profile.label}' do usuário {user.name}: {e}", exc_info=True)
    finally:
        if close_db_at_end:
            db.close()


def run_pipeline_for_resume(user: User, resume_profile: Resume, seen_store: SeenJobStore, db):
    scope_id = str(resume_profile.id)
    log.info(f"\n--- Processando Perfil: '{resume_profile.label}' (ID: {scope_id}) ---")
    log.info(f"    Cargos: {resume_profile.keyword_roles}")
    log.info(f"    Setores: {resume_profile.target_sectors or 'Todos'}")
    log.info(f"    Empresas-alvo: {resume_profile.target_companies or 'Nenhuma'}")
    log.info(f"    Empresas excluídas: {resume_profile.excluded_companies or 'Nenhuma'}")

    # Garante o perfil estruturado em cache no banco
    parsed_resume = resume_profile.parsed_profile
    if not parsed_resume:
        log.info("Perfil ainda não estruturado via LLM. Parseando agora...")
        parsed_resume = parse_resume(resume_profile.resume_pdf)
        resume_profile.parsed_profile = parsed_resume
        db.add(resume_profile)
        db.commit()

    builder = BooleanQueryBuilder(
        keyword_roles=resume_profile.keyword_roles or [],
        keyword_locations=resume_profile.keyword_locations or [],
        keyword_levels=resume_profile.keyword_levels or [],
        target_sectors=resume_profile.target_sectors or [],
        target_companies=resume_profile.target_companies or [],
    )
    queries = builder.all_queries()
    notified = 0

    # =========================================================================
    # FASE 1 — Coleta de URLs e scraping
    # =========================================================================
    log.info("=== FASE 1: Coleta de URLs ===")
    all_urls: list[str] = []

    for item in queries:
        site  = item["site"]
        query = item["query"]

        if not seen_store.is_new_query(query):
            log.info(f"  [query-skip] Query executada recentemente [{site}]")
            continue

        log.info(f"Buscando [{site}]: {query}")
        seen_store.mark_query(query)

        try:
            links = search_links(query)
            log.info(f"  -> {len(links)} links encontrados")
        except Exception as e:
            log.warning(f"  Erro ao buscar links no SerpAPI para query '{query}': {e}")
            continue

        new_links = [url for url in links if seen_store.is_new_url(url)]
        skipped = len(links) - len(new_links)
        if skipped:
            log.info(f"  -> {skipped} URL(s) já conhecidas em cache global, ignoradas")

        all_urls.extend(new_links)

    all_urls = list(dict.fromkeys(all_urls))
    log.info(f"Total de URLs novas para scraping: {len(all_urls)}")

    if not all_urls:
        log.info(f"Nenhuma URL nova para o perfil '{resume_profile.label}'.")
        return

    scraped_pages = scrape_many(all_urls, workers=settings.scrape_workers)
    log.info(f"Scraping concluído: {len(scraped_pages)}/{len(all_urls)} páginas coletadas")

    for page in scraped_pages:
        seen_store.mark_url(page["url"])

    # =========================================================================
    # FASE 2 — Filtragem barata sem LLM
    # =========================================================================
    log.info("=== FASE 2: Filtragem barata sem LLM ===")
    candidates: list[dict] = []

    for page in scraped_pages:
        title, company = extract_title_cheap(page)

        if not title:
            candidates.append(page)
            continue

        if not seen_store.is_new_job(title, company, scope=scope_id):
            log.info(f"  [dedup] Vaga já notificada para este perfil: '{title}' @ '{company}'")
            continue

        page["_cheap_title"]   = title
        page["_cheap_company"] = company
        candidates.append(page)

    log.info(f"Candidatas após filtro barato: {len(candidates)}/{len(scraped_pages)}")

    # =========================================================================
    # FASE 3 — Processamento: Gemini extract + Filtro Setor + Match + WhatsApp
    # =========================================================================
    log.info("=== FASE 3: Extração Gemini + Filtro Setorial/Empresas + Match ===")
    limit = settings.max_notifications_per_run

    for page in candidates:
        if notified >= limit:
            log.info(f"Limite de {limit} notificações atingido para o perfil '{resume_profile.label}'.")
            break

        url = page.get("url", "")
        job = extract_job(page)
        if not job:
            log.warning(f"  Falha na extração de dados da vaga: {url}")
            continue

        title   = job.get("title", "") or ""
        company = job.get("company", "") or ""

        if not seen_store.is_new_job(title, company, scope=scope_id):
            log.info(f"  [dedup-gemini] Vaga já enviada para este perfil: '{title}' @ '{company}'")
            continue

        # 3.1 Filtro de Localização
        loc_ok, loc_reason = is_location_acceptable(job)
        if not loc_ok:
            log.info(f"  [loc-filter] Rejeitada: {loc_reason} | '{title}' @ '{company}'")
            continue

        # 3.2 Filtro RÍGIDO de Setor / Empresas-Alvo
        sec_ok, sec_reason = is_sector_acceptable(
            job=job,
            target_sectors=resume_profile.target_sectors,
            target_companies=resume_profile.target_companies,
            excluded_companies=resume_profile.excluded_companies,
        )
        if not sec_ok:
            log.info(f"  [sector-filter] Rejeitada: {sec_reason} | '{title}' @ '{company}'")
            continue

        # 3.3 Score e compatibilidade com o currículo do perfil
        result = match(job, parsed_resume)
        score  = result.get("score", 0)
        label  = "ACIMA" if score >= settings.min_score_to_notify else "ABAIXO"

        log.info(f"  [{label} do mínimo ({score}/100)] {title} @ {company} [{sec_reason}]")

        if score >= settings.min_score_to_notify:
            sent = send_to_target(result, user.phone, profile_label=resume_profile.label)
            if sent:
                seen_store.mark_job(title, company, scope=scope_id)
                notified += 1
                log.info(f"    🚀 Enviado para {user.name} ({notified}/{limit})!")

    log.info(f"Perfil '{resume_profile.label}' concluído. {notified} novas vagas enviadas.")


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
        minute="0",
    ))

    log.info("Agendador iniciado — rodando às 08:00, 10:00, 13:00, 16:00 (BRT)")
    log.info("Executando pipeline inicial...")
    job()

    try:
        scheduler.start()
    except KeyboardInterrupt:
        log.info("Agendador encerrado.")