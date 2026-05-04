# test_sprint6.py
"""
Sprint 6 - Testes de deduplicacao de vagas (SeenJobStore)

Cobre:
  1. Deduplicacao por URL (mesma URL exata)
  2. Deduplicacao por URL com variantes de LinkedIn (slug/trk diferentes)
  3. Deduplicacao semantica cross-site (mesmo titulo+empresa, sites distintos)
  4. Normalizacao tolerante a seniority/stopwords no titulo
  5. Persistencia em disco (save -> novo store -> load)
  6. Vagas distintas NAO sao bloqueadas
"""
import json
import tempfile
from pathlib import Path
from agent.seen_store import SeenJobStore, _normalize_url, _job_fingerprint, _JsonBackend

PASS = "[PASS]"
FAIL = "[FAIL]"
results = []


def check(label: str, condition: bool) -> None:
    status = PASS if condition else FAIL
    results.append((status, label))
    print(f"  {status} {label}")


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def make_store(tmp_dir: Path) -> SeenJobStore:
    """Cria SeenJobStore isolado com backend JSON temporario (sem Redis)."""
    store = SeenJobStore.__new__(SeenJobStore)
    store._backend = _JsonBackend(tmp_dir / "seen_jobs.json")
    store._using_redis = False
    return store


# -----------------------------------------------------------------------------
# Suite 1 - Normalizacao de URL
# -----------------------------------------------------------------------------
print("\n--- Suite 1: Normalizacao de URL ---")

linkedin_base  = "https://www.linkedin.com/jobs/view/1234567890/"
linkedin_slug  = "https://www.linkedin.com/jobs/view/1234567890/Analista-Junior-Transportes"
linkedin_trk   = "https://www.linkedin.com/jobs/view/1234567890/?trk=serpapi&refId=abc"
linkedin_other = "https://www.linkedin.com/jobs/view/9999999999/"

check(
    "LinkedIn: URL base e URL com slug geram mesma chave",
    _normalize_url(linkedin_base) == _normalize_url(linkedin_slug),
)
check(
    "LinkedIn: URL com ?trk= gera mesma chave que URL limpa",
    _normalize_url(linkedin_base) == _normalize_url(linkedin_trk),
)
check(
    "LinkedIn: IDs distintos geram chaves distintas",
    _normalize_url(linkedin_base) != _normalize_url(linkedin_other),
)

catho_clean = "https://www.catho.com.br/vagas/analista-junior"
catho_utm   = "https://www.catho.com.br/vagas/analista-junior?utm_source=serpapi&ref=google"
check(
    "Catho: URL com query-string gera mesma chave que URL limpa",
    _normalize_url(catho_clean) == _normalize_url(catho_utm),
)
check(
    "Catho vs LinkedIn: sites distintos tem chaves distintas",
    _normalize_url(catho_clean) != _normalize_url(linkedin_base),
)

# -----------------------------------------------------------------------------
# Suite 2 - Fingerprint semantico
# -----------------------------------------------------------------------------
print("\n--- Suite 2: Fingerprint semantico (titulo + empresa) ---")

# Regressao: caso real observado em producao (Shopee duplicata)
check(
    "[REGRESSAO] Titulo com sufixo de cidade '-Barueri/SP' == titulo limpo",
    _job_fingerprint("Analista Junior de Transportes - Barueri/SP", "Shopee")
    == _job_fingerprint("Analista Junior de Transportes", "Shopee"),
)
check(
    "[REGRESSAO] Titulo com separador '|' e cidade == titulo limpo",
    _job_fingerprint("Analista Junior de Transportes | Sao Paulo", "Shopee")
    == _job_fingerprint("Analista Junior de Transportes", "Shopee"),
)

check(
    "Titulo identico -> mesma chave",
    _job_fingerprint("Analista de Transportes", "Shopee")
    == _job_fingerprint("Analista de Transportes", "Shopee"),
)
check(
    "Variacao de seniority 'Junior' vs 'Jr' -> mesma chave",
    _job_fingerprint("Analista Junior de Transportes", "Shopee")
    == _job_fingerprint("Analista Jr de Transportes", "Shopee"),
)
check(
    "Ordem de palavras diferente -> mesma chave (tokens ordenados)",
    _job_fingerprint("Analista de Transportes Junior", "Shopee")
    == _job_fingerprint("Junior Analista de Transportes", "Shopee"),
)
check(
    "Acento vs sem acento -> mesma chave",
    _job_fingerprint("Analista Sênior de Logística", "Shopee")
    == _job_fingerprint("Analista Senior de Logistica", "Shopee"),
)
check(
    "Empresa diferente -> chave diferente",
    _job_fingerprint("Analista de Transportes", "Shopee")
    != _job_fingerprint("Analista de Transportes", "Mercado Livre"),
)
check(
    "Titulo diferente -> chave diferente",
    _job_fingerprint("Analista de Transportes", "Shopee")
    != _job_fingerprint("Analista de Supply Chain", "Shopee"),
)

# -----------------------------------------------------------------------------
# Suite 3 - SeenJobStore: Camada 1 (URL)
# -----------------------------------------------------------------------------
print("\n--- Suite 3: SeenJobStore - Camada 1 (URL) ---")

with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    store = make_store(tmp_path)

    check("URL nova e aceita (is_new_url=True)",              store.is_new_url(linkedin_base))
    store.mark_url(linkedin_base)
    check("URL registrada e bloqueada (is_new_url=False)",    not store.is_new_url(linkedin_base))
    check("Variante LinkedIn slug tambem e bloqueada",        not store.is_new_url(linkedin_slug))
    check("Variante LinkedIn ?trk= tambem e bloqueada",       not store.is_new_url(linkedin_trk))
    check("URL de outro site continua livre",                  store.is_new_url(catho_clean))

# -----------------------------------------------------------------------------
# Suite 4 - SeenJobStore: Camada 2 (semantica)
# -----------------------------------------------------------------------------
print("\n--- Suite 4: SeenJobStore - Camada 2 (semantica / cross-site) ---")

with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    store = make_store(tmp_path)

    title   = "Analista Junior de Transportes"
    company = "Shopee"

    check("Vaga nova e aceita (is_new_job=True)",             store.is_new_job(title, company))
    store.mark_job(title, company)
    check("Apos mark_job: vaga exata e bloqueada",            not store.is_new_job(title, company))
    check("Variante 'Jr' tambem e bloqueada",                 not store.is_new_job("Analista Jr de Transportes", company))
    check("Variante com acento e bloqueada",                  not store.is_new_job("Analista Junior de Transportes", company))
    check("Mesma vaga, empresa diferente: ainda aceita",       store.is_new_job(title, "Mercado Livre"))
    check("Titulo diferente, mesma empresa: ainda aceita",     store.is_new_job("Analista de Supply Chain", company))

# -----------------------------------------------------------------------------
# Suite 5 - Persistencia em disco
# -----------------------------------------------------------------------------
print("\n--- Suite 5: Persistencia em disco ---")

with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    json_path = tmp_path / "seen_jobs.json"

    store1 = make_store(tmp_path)
    store1.mark_url(linkedin_base)
    store1.mark_job("Analista de Transportes", "Shopee")

    check("Arquivo seen_jobs.json foi criado",             json_path.exists())

    data = json.loads(json_path.read_text(encoding="utf-8"))
    check("Chave 'seen_urls' existe no JSON",              "seen_urls" in data)
    check("Chave 'seen_jobs' existe no JSON",              "seen_jobs" in data)
    check("URL esta registrada no JSON",                   len(data["seen_urls"]) == 1)
    check("Job esta registrado no JSON",                   len(data["seen_jobs"]) == 1)

    store2 = make_store(tmp_path)
    check("Novo store carrega URL do disco corretamente",          not store2.is_new_url(linkedin_base))
    check("Novo store carrega vaga semantica do disco corretamente",
          not store2.is_new_job("Analista de Transportes", "Shopee"))

# -----------------------------------------------------------------------------
# Suite 6 - Vagas distintas nao interferem entre si
# -----------------------------------------------------------------------------
print("\n--- Suite 6: Vagas distintas nao interferem entre si ---")

with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    store = make_store(tmp_path)

    vagas = [
        ("Analista de Logistica", "Shopee"),
        ("Coordenador de Supply Chain", "Mercado Livre"),
        ("Assistente de Operacoes", "Amazon"),
        ("Analista de Transportes", "Rappi"),
    ]

    for titulo, empresa in vagas:
        store.mark_job(titulo, empresa)

    for titulo, empresa in vagas:
        check(f"'{titulo} @ {empresa}' bloqueada corretamente", not store.is_new_job(titulo, empresa))

    check(
        "Vaga fora da lista permanece livre",
        store.is_new_job("Gerente de Projetos", "Shopee"),
    )

# -----------------------------------------------------------------------------
# Resultado final
# -----------------------------------------------------------------------------
total  = len(results)
passed = sum(1 for s, _ in results if s == PASS)
failed = total - passed

print(f"\n{'='*52}")
print(f"Sprint 6 - Resultado: {passed}/{total} testes passaram")
if failed:
    print(f"\nFalhas:")
    for status, label in results:
        if status == FAIL:
            print(f"  {FAIL} {label}")
else:
    print("Todos os testes passaram!")
print(f"{'='*52}\n")
