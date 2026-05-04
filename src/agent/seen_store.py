# agent/seen_store.py
"""
Armazena vagas ja processadas usando Redis com TTL de 30 dias (configuravel).

Estrategia:
  - Chave URL:  "job:url:<hash>"  — evita reprocessar o mesmo link
  - Chave Job:  "job:sem:<hash>"  — evita reenviar a mesma vaga (title+company)
                                    de sites diferentes
  - TTL: 30 dias por padrao (REDIS_TTL_DAYS no .env)

Fallback:
  - Se o Redis nao estiver disponivel, cai para armazenamento em JSON local
    (comportamento anterior), logando um aviso.

Normalizacao:
  - LinkedIn: extrai job-ID numerico da URL (ignora slug e query-params)
  - Outros:   remove query-string e fragment antes do MD5
  - Titulo:   remove sufixos de localizacao (- Barueri/SP, | SP...)
              e stop-words/siglas de estado antes do fingerprint
"""
import re
import json
import hashlib
import logging
from pathlib import Path
from urllib.parse import urlparse, urlunparse

log = logging.getLogger(__name__)

_FALLBACK_PATH = Path(__file__).resolve().parent.parent / "output" / "seen_jobs.json"

# Prefixos de chave no Redis
_PREFIX_URL = "job:url:"
_PREFIX_SEM = "job:sem:"
_PREFIX_QRY = "job:qry:"  # queries ja executadas (TTL 1 dia)


# ──────────────────────────────────────────────────────────────────────────────
# Normalizacao de URL
# ──────────────────────────────────────────────────────────────────────────────

def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    if "linkedin.com" in parsed.netloc:
        parts = [p for p in parsed.path.split("/") if p]
        try:
            view_idx = parts.index("view")
            return f"linkedin:{parts[view_idx + 1]}"
        except (ValueError, IndexError):
            pass
    clean = urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))
    return hashlib.md5(clean.encode()).hexdigest()


# ──────────────────────────────────────────────────────────────────────────────
# Normalizacao semantica (title + company)
# ──────────────────────────────────────────────────────────────────────────────

_STOP_WORDS = {
    "de", "da", "do", "das", "dos", "em", "para", "e", "ou",
    "jr", "sr", "pl", "junior", "pleno", "senior",
    "analyst", "analista", "assistente", "assistant",
    # siglas de estados
    "sp", "rj", "mg", "rs", "pr", "sc", "ba", "go", "df", "pe",
    "ce", "am", "pa", "mt", "ms", "es", "rn", "pi", "al", "se",
}

_LOCATION_SUFFIX_RE = re.compile(r"[\-\|\u2013\u2014]\s*.{2,40}$", re.IGNORECASE)


def _normalize_text(text: str) -> str:
    text = (text or "").lower().strip()
    text = _LOCATION_SUFFIX_RE.sub("", text).strip()
    for src, dst in [
        ("ã", "a"), ("â", "a"), ("á", "a"), ("à", "a"), ("ä", "a"),
        ("ê", "e"), ("é", "e"), ("è", "e"), ("ë", "e"),
        ("î", "i"), ("í", "i"), ("ï", "i"),
        ("ô", "o"), ("ó", "o"), ("õ", "o"), ("ö", "o"),
        ("û", "u"), ("ú", "u"), ("ü", "u"),
        ("ç", "c"), ("ñ", "n"),
    ]:
        text = text.replace(src, dst)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    tokens = [t for t in text.split() if t and t not in _STOP_WORDS and len(t) > 1]
    return " ".join(sorted(tokens))


def _job_fingerprint(title: str, company: str) -> str:
    key = f"{_normalize_text(title)}|{_normalize_text(company)}"
    return hashlib.md5(key.encode()).hexdigest()


# ──────────────────────────────────────────────────────────────────────────────
# Backend Redis
# ──────────────────────────────────────────────────────────────────────────────

class _RedisBackend:
    def __init__(self, redis_url: str, ttl_seconds: int):
        import redis as redis_lib
        self._r = redis_lib.from_url(redis_url, decode_responses=True)
        self._r.ping()  # valida conexao na inicializacao
        self._ttl = ttl_seconds
        log.info(f"Redis conectado: {redis_url} | TTL: {ttl_seconds // 86400} dias")

    def exists(self, key: str) -> bool:
        return self._r.exists(key) == 1

    def set(self, key: str) -> None:
        self._r.setex(key, self._ttl, "1")

    def query_exists(self, query_hash: str) -> bool:
        """True se esta query ja foi executada hoje."""
        return self._r.exists(_PREFIX_QRY + query_hash) == 1

    def mark_query(self, query_hash: str) -> None:
        """Registra a query como executada com TTL de 1 dia."""
        self._r.setex(_PREFIX_QRY + query_hash, 86_400, "1")

    def count(self) -> int:
        """Conta chaves de vagas no banco atual (aproximado)."""
        return sum(1 for _ in self._r.scan_iter(f"{_PREFIX_URL}*"))


# ──────────────────────────────────────────────────────────────────────────────
# Backend JSON (fallback local)
# ──────────────────────────────────────────────────────────────────────────────

class _JsonBackend:
    def __init__(self, path: Path = _FALLBACK_PATH):
        self._path = path
        self._url_keys: set[str] = set()
        self._sem_keys: set[str] = set()
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._url_keys = set(data.get("seen_urls", []))
                self._sem_keys = set(data.get("seen_jobs", []))
            except Exception as e:
                log.warning(f"JSON fallback: erro ao carregar: {e}")

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(
                {"seen_urls": sorted(self._url_keys), "seen_jobs": sorted(self._sem_keys)},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )

    def exists(self, key: str) -> bool:
        return key in self._url_keys or key in self._sem_keys

    def _is_url_key(self, key: str) -> bool:
        return key.startswith(_PREFIX_URL)

    def set(self, key: str) -> None:
        if self._is_url_key(key):
            self._url_keys.add(key)
        else:
            self._sem_keys.add(key)
        self._save()

    def query_exists(self, query_hash: str) -> bool:
        """JSON backend nao persiste queries — sempre retorna False."""
        return False

    def mark_query(self, query_hash: str) -> None:
        """JSON backend nao persiste queries — sem efeito."""
        pass

    def count(self) -> int:
        return len(self._url_keys)


# ──────────────────────────────────────────────────────────────────────────────
# SeenJobStore — interface publica
# ──────────────────────────────────────────────────────────────────────────────

class SeenJobStore:
    """
    Gerencia vagas ja processadas com TTL automatico via Redis.

    Duas camadas:
      1. URL-based  (is_new_url / mark_url)  — evita reprocessar o mesmo link
      2. Semantica  (is_new_job / mark_job)  — evita reenviar a mesma vaga
                                               de sites diferentes

    TTL configuravel em REDIS_TTL_DAYS (default 30 dias).
    Se o Redis nao estiver disponivel, usa arquivo JSON local como fallback.
    """

    def __init__(self):
        from config.settings import settings
        ttl_seconds = settings.redis_ttl_days * 86_400
        try:
            self._backend = _RedisBackend(settings.redis_url, ttl_seconds)
            self._using_redis = True
        except Exception as e:
            log.warning(
                f"Redis indisponivel ({e}). Usando fallback JSON em '{_FALLBACK_PATH}'."
            )
            self._backend = _JsonBackend()
            self._using_redis = False

        count = self._backend.count()
        storage = "Redis" if self._using_redis else "JSON"
        log.info(f"SeenJobStore iniciado [{storage}] — ~{count} URLs registradas.")

    # ── Camada 1: URL ─────────────────────────────────────────────────────────

    def is_new_url(self, url: str) -> bool:
        """True se esta URL ainda nao foi processada."""
        return not self._backend.exists(_PREFIX_URL + _normalize_url(url))

    def mark_url(self, url: str) -> None:
        """Registra a URL como processada (com TTL no Redis)."""
        self._backend.set(_PREFIX_URL + _normalize_url(url))

    # ── Camada 2: Semantica (title + company) ─────────────────────────────────

    def is_new_job(self, title: str, company: str) -> bool:
        """True se esta combinacao titulo+empresa ainda nao foi notificada."""
        return not self._backend.exists(_PREFIX_SEM + _job_fingerprint(title, company))

    def mark_job(self, title: str, company: str) -> None:
        """Registra o par (titulo, empresa) como notificado (com TTL no Redis)."""
        self._backend.set(_PREFIX_SEM + _job_fingerprint(title, company))

    # ── Camada 3: Rastreamento de queries ────────────────────────────────────

    def is_new_query(self, query: str) -> bool:
        """
        True se esta query ainda nao foi executada na ultima execucao.
        Permite forcara o sistema a usar queries diferentes a cada rodada.
        Apenas funcional com backend Redis; com JSON sempre retorna True.
        """
        query_hash = hashlib.md5(query.strip().encode()).hexdigest()
        return not self._backend.query_exists(query_hash)

    def mark_query(self, query: str) -> None:
        """Registra a query como executada (expira em 1 dia automaticamente)."""
        query_hash = hashlib.md5(query.strip().encode()).hexdigest()
        self._backend.mark_query(query_hash)

    # ── Retrocompatibilidade ──────────────────────────────────────────────────

    def is_new(self, url: str) -> bool:
        return self.is_new_url(url)

    def mark_seen(self, url: str) -> None:
        self.mark_url(url)

    def __len__(self) -> int:
        return self._backend.count()
