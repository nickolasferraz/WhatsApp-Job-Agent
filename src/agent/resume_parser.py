import json
import io
import logging
import pdfplumber
from google import genai
from google.genai import types
from config.settings import settings

log = logging.getLogger(__name__)

client = genai.Client(api_key=settings.gemini_api_key)

SYSTEM_PROMPT = """
Você é um extrator e estruturador de currículos profissionais de qualquer segmento
(TI, Engenharia, Indústria Automotiva, Logística, Supply Chain, Finanças, Saúde, etc.).

Dado o texto bruto de um currículo, extraia e retorne SOMENTE um JSON válido com a seguinte estrutura:
{
  "name": "nome completo",
  "target_roles": ["cargos ou áreas que a pessoa busca ou atua"],
  "skills": ["lista de competências técnicas, operacionais e comportamentais"],
  "industries": ["setores ou indústrias em que possui experiência (ex: automotivo, logistica, varejo)"],
  "languages": ["idiomas dominados"],
  "seniority": "estagio | junior | pleno | senior | lideranca | especialista",
  "locations_accepted": ["cidades, regiões ou países aceitos"],
  "work_modes_accepted": ["remote | hybrid | on-site"],
  "summary": "resumo de 3 linhas sobre a trajetória e perfil do profissional em pt-BR"
}
Responda ESTRITAMENTE o JSON, sem blocos markdown (sem ```json), sem explicações.
"""

def read_pdf(source: str | bytes) -> str:
    """
    Extrai o texto de um PDF a partir de um caminho em disco (str) ou bytes em memória.
    """
    if isinstance(source, bytes):
        stream = io.BytesIO(source)
        with pdfplumber.open(stream) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    else:
        with pdfplumber.open(source) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)

def parse_resume(source: str | bytes) -> dict:
    """
    Converte um currículo em PDF (caminho ou bytes) para o perfil estruturado via Gemini.
    """
    raw_text = read_pdf(source)
    if not raw_text.strip():
        return {
            "name": "",
            "target_roles": [],
            "skills": [],
            "industries": [],
            "languages": [],
            "seniority": "pleno",
            "locations_accepted": [],
            "work_modes_accepted": [],
            "summary": "",
            "raw_text": "",
        }

    model_name = getattr(settings, "ia_version", None) or "gemini-2.5-flash"
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=raw_text[:6000],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0,
            ),
        )

        raw_json = response.text.strip()
        if raw_json.startswith("```"):
            raw_json = raw_json.split("```")[1]
            if raw_json.startswith("json"):
                raw_json = raw_json[4:]

        profile = json.loads(raw_json)
    except Exception as e:
        log.warning(f"Erro ao parsear currículo via LLM: {e}")
        profile = {
            "name": "",
            "target_roles": [],
            "skills": [],
            "industries": [],
            "languages": [],
            "seniority": "pleno",
            "locations_accepted": [],
            "work_modes_accepted": [],
            "summary": "Perfil extraído automaticamente com dados básicos.",
        }

    profile["raw_text"] = raw_text
    return profile
