# agent/extractor.py
import re
import json
import logging
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from config.settings import settings
from config.sectors import sectors_for_prompt

log = logging.getLogger(__name__)

client = genai.Client(api_key=settings.gemini_api_key)

SYSTEM_PROMPT = f"""
Você é um extrator e analisador especializado em vagas de emprego de todos os segmentos
(Indústria Automotiva, Manufatura, Logística, Tecnologia, Varejo, Saúde, Finanças, etc.).

Dado o texto bruto de uma página de vaga, sua missão é:
1. Detectar o idioma e extrair os dados da vaga.
2. Identificar a empresa contratante e o seu setor/ramo de atuação (indústria).

Setores válidos da empresa contratante (escolha um ou mais aplicáveis):
{sectors_for_prompt()}

Retorne SOMENTE um JSON com a estrutura abaixo, sem markdown, sem explicações:
{{
  "title": "titulo da vaga",
  "company": "nome da empresa contratante",
  "location": "cidade/estado ou null",
  "work_mode": "remote | hybrid | on-site",
  "contract_type": "CLT | PJ | estagio | temporario | null",
  "seniority": "estagio | junior | pleno | senior | lideranca | especialista",
  "salary_range": "faixa salarial ou null",
  "description": "resumo objetivo da vaga em 3 linhas",
  "requirements": ["requisito 1", "requisito 2"],
  "nice_to_have": ["diferencial 1", "diferencial 2"],
  "languages": ["idiomas exigidos ou aceitos"],
  "industries": ["chaves dos setores identificados na lista acima"],
  "industry_description": "breve explicacao do ramo da empresa (ex: montadora de veiculos pesados, operador logistico 3PL, etc.)",
  "contact": {{
    "name": "nome do recrutador ou null",
    "email": "email ou null",
    "phone": "telefone ou null"
  }},
  "job_language": "pt | en | es | outros"
}}
"""

# ---------------------------------------------------------------------------
# Extrator barato — sem LLM (Fase 2)
# ---------------------------------------------------------------------------

_TITLE_SELECTORS = [
    "h1",
    '[class*="job-title"]',
    '[class*="jobTitle"]',
    '[class*="title"]',
    '[data-test="job-title"]',
    "title",
]

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
    """
    html = scraped.get("html", "")
    text = scraped.get("text", "")

    title   = ""
    company = ""

    if html:
        soup = BeautifulSoup(html, "lxml")

        for selector in _TITLE_SELECTORS:
            el = soup.select_one(selector)
            if el:
                candidate = el.get_text(strip=True)
                if 5 < len(candidate) < 120:
                    title = candidate
                    break

        for selector in _COMPANY_SELECTORS:
            el = soup.select_one(selector)
            if el:
                candidate = el.get_text(strip=True)
                if 2 < len(candidate) < 80:
                    company = candidate
                    break

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


def extract_job(scraped: dict, resume: str = "") -> dict | None:
    """
    Extrai dados completos da vaga e classificação do setor da empresa via Gemini.
    """
    try:
        content = f"""
=== TEXTO DA VAGA ===
{scraped.get("text", "")[:5000]}
"""
        model_name = getattr(settings, "ia_version", None) or "gemini-2.5-flash"
        response = client.models.generate_content(
            model=model_name,
            contents=content,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0,
            ),
        )

        job = _parse_llm_response(response.text)
        job["url"] = scraped.get("url", "")
        job["id"]  = scraped.get("id", "")
        if "industries" not in job or not isinstance(job["industries"], list):
            job["industries"] = []
        return job

    except Exception as e:
        log.warning(f"  [extractor] Erro ao extrair vaga {scraped.get('url', '')}: {e}")
        return None


_TRANSLATE_PROMPT = """
Você é um tradutor profissional especializado em currículos profissionais.
Traduza o currículo abaixo do português para o inglês americano.

Regras:
- Preserve toda a formatação, bullets e estrutura
- Adapte termos técnicos e cargos para o padrão do mercado internacional
- Mantenha nomes próprios, nomes de empresas e siglas sem traduzir
- Não adicione nem remova informações
- Retorne APENAS o currículo traduzido, sem explicações
"""

def translate_resume_to_english(resume_pt: str) -> str:
    if not resume_pt:
        return ""
        
    try:
        model_name = getattr(settings, "ia_version", None) or "gemini-2.5-flash"
        response = client.models.generate_content(
            model=model_name,
            contents=resume_pt,
            config=types.GenerateContentConfig(
                system_instruction=_TRANSLATE_PROMPT,
                temperature=0,
            ),
        )
        return response.text.strip()
    except Exception as e:
        log.warning(f"  [extractor] Erro ao traduzir currículo: {e}")
        return resume_pt