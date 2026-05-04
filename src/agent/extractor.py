# agent/extractor.py
import re
import json
import logging
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from config.settings import settings

log = logging.getLogger(__name__)

client = genai.Client(api_key=settings.gemini_api_key)

SYSTEM_PROMPT = """
Voce e um extrator de dados de vagas de emprego.
Dado o texto bruto de uma pagina de vaga, retorne SOMENTE um JSON com:
{
  "title": "titulo da vaga",
  "company": "nome da empresa",
  "location": "cidade/estado",
  "work_mode": "remote | hybrid | on-site",
  "seniority": "junior | pleno | senior",
  "salary_range": "faixa salarial ou null",
  "description": "resumo da vaga em 3 linhas",
  "requirements": ["requisito 1", "requisito 2"],
  "nice_to_have": ["diferencial 1", "diferencial 2"],
  "languages": ["idiomas exigidos"],
  "contact": {
    "name": "nome do recrutador ou null",
    "email": "email ou null",
    "phone": "telefone ou null"
  }
}
Responda SOMENTE o JSON, sem markdown, sem explicacoes.
"""

# ---------------------------------------------------------------------------
# Extrator barato — sem LLM (Fase 2)
# ---------------------------------------------------------------------------

# Seletores CSS tentados em ordem para achar o titulo da vaga
_TITLE_SELECTORS = [
    "h1",
    '[class*="job-title"]',
    '[class*="jobTitle"]',
    '[class*="title"]',
    '[data-test="job-title"]',
    "title",
]

# Seletores para empresa
_COMPANY_SELECTORS = [
    '[class*="company"]',
    '[class*="employer"]',
    '[data-test="company-name"]',
    '[class*="organization"]',
]


def extract_title_cheap(scraped: dict) -> tuple[str, str]:
    """
    Extrai titulo e empresa da pagina HTML usando BeautifulSoup, sem chamar o Gemini.

    Usado na Fase 2 para dedup barata antes de gastar tokens de LLM.

    Returns:
        (title, company) — strings vazias se nao encontrado.
    """
    html = scraped.get("html", "")
    text = scraped.get("text", "")

    title   = ""
    company = ""

    if html:
        soup = BeautifulSoup(html, "lxml")

        # Tenta extrair titulo
        for selector in _TITLE_SELECTORS:
            el = soup.select_one(selector)
            if el:
                candidate = el.get_text(strip=True)
                # Descarta se muito curto ou muito longo (provavelmente nao e o titulo)
                if 5 < len(candidate) < 120:
                    title = candidate
                    break

        # Tenta extrair empresa
        for selector in _COMPANY_SELECTORS:
            el = soup.select_one(selector)
            if el:
                candidate = el.get_text(strip=True)
                if 2 < len(candidate) < 80:
                    company = candidate
                    break

    # Fallback: tenta extrair da primeira linha do texto bruto que pareça um título
    if not title and text:
        for line in text.splitlines():
            line = line.strip()
            if 10 < len(line) < 100 and not line.startswith("http"):
                title = line
                break

    log.debug(f"  [cheap] title='{title}' company='{company}'")
    return title, company


# ---------------------------------------------------------------------------
# Extrator completo via Gemini (Fase 3)
# ---------------------------------------------------------------------------

def _parse_llm_response(raw: str) -> dict:
    """Remove markdown fences e faz parse do JSON retornado pelo Gemini."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


def extract_job(scraped: dict) -> dict | None:
    """
    Extrai dados completos da vaga via Gemini (chamada LLM paga).
    So deve ser chamado apos a filtragem barata da Fase 2.
    """
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=scraped["text"][:6000],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0,
            ),
        )

        job = _parse_llm_response(response.text)
        job["url"] = scraped["url"]
        job["id"]  = scraped["id"]
        return job

    except Exception as e:
        log.warning(f"  [extractor] Erro ao extrair vaga {scraped.get('url', '')}: {e}")
        return None