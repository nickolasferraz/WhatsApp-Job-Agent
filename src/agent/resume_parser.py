import json
import pdfplumber
from google import genai
from google.genai import types
from config.settings import settings

client = genai.Client(api_key=settings.gemini_api_key)

SYSTEM_PROMPT = """
Você é um extrator de dados de currículo.
Dado o texto bruto de um currículo, retorne SOMENTE um JSON com os campos:
{
  "name": "nome completo",
  "target_roles": ["cargos que a pessoa busca"],
  "skills": ["lista de skills técnicas e comportamentais"],
  "languages": ["idiomas que fala"],
  "seniority": "junior | pleno | senior",
  "locations_accepted": ["cidades ou regiões aceitas"],
  "work_modes_accepted": ["remote | hybrid | on-site"],
  "summary": "resumo de 3 linhas sobre o profissional em pt-BR"
}
Responda SOMENTE o JSON, sem markdown, sem explicações.
"""

def read_pdf(path: str) -> str:
    with pdfplumber.open(path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)

def parse_resume(path: str) -> dict:
    raw_text = read_pdf(path)

    response = client.models.generate_content(
        model=settings.ia_version,
        contents=raw_text[:5000],
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0,
        ),
    )

    raw_json = response.text.strip()

    # Remove markdown se o modelo retornar com ```json
    if raw_json.startswith("```"):
        raw_json = raw_json.split("```")[1]
        if raw_json.startswith("json"):
            raw_json = raw_json[4:]

    profile = json.loads(raw_json)
    profile["raw_text"] = raw_text
    return profile
