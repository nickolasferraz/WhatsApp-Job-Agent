# agent/matcher.py
import json
from rapidfuzz import fuzz
from google import genai
from google.genai import types
from config.settings import settings

client = genai.Client(api_key=settings.gemini_api_key)

# Pesos do score objetivo (70% do total)
WEIGHTS = {
    "skills":    0.35,
    "seniority": 0.20,
    "location":  0.15,
    "language":  0.15,
    "title":     0.15,
}

def _skill_score(job: dict, resume: dict) -> float:
    reqs = job.get("requirements", [])
    if not reqs:
        return 0.5
    skills = resume.get("skills", [])
    hits = sum(
        1 for req in reqs
        if any(fuzz.partial_ratio(req.lower(), sk.lower()) > 75 for sk in skills)
    )
    return hits / len(reqs)

def _seniority_score(job: dict, resume: dict) -> float:
    job_sen = (job.get("seniority") or "").lower()
    res_sen = (resume.get("seniority") or "").lower()
    if not job_sen:
        return 0.7
    return 1.0 if job_sen == res_sen else 0.3

def _location_score(job: dict, resume: dict) -> float:
    job_loc  = (job.get("location") or "").lower()
    job_mode = (job.get("work_mode") or "").lower()
    accepted = [l.lower() for l in resume.get("locations_accepted", [])]
    modes    = [m.lower() for m in resume.get("work_modes_accepted", [])]
    if not job_loc:
        return 0.8
    loc_ok  = any(loc in job_loc for loc in accepted)
    mode_ok = any(m in job_mode for m in modes)
    return 1.0 if (loc_ok or mode_ok) else 0.2

def _language_score(job: dict, resume: dict) -> float:
    raw_langs = job.get("languages") or []
    job_langs = [(l or "").lower() for l in raw_langs if l]
    res_langs = [(l or "").lower() for l in resume.get("languages", []) if l]
    if not job_langs:
        return 1.0
    covered = sum(1 for lang in job_langs if any(lang in r for r in res_langs))
    return covered / len(job_langs)

def _title_score(job: dict, resume: dict) -> float:
    # Usa 'or ""' para tratar explicitamente valores null vindos do LLM
    title = (job.get("title") or "").lower()
    roles = resume.get("target_roles", []) or []
    if not roles:
        return 0.5
    return max(fuzz.partial_ratio((role or "").lower(), title) / 100 for role in roles)

def _objective_score(job: dict, resume: dict) -> int:
    scores = {
        "skills":    _skill_score(job, resume),
        "seniority": _seniority_score(job, resume),
        "location":  _location_score(job, resume),
        "language":  _language_score(job, resume),
        "title":     _title_score(job, resume),
    }
    return int(sum(scores[k] * WEIGHTS[k] for k in scores) * 100)

LLM_PROMPT = """
Analise a compatibilidade do candidato com a vaga e responda SOMENTE JSON:
{{
  "llm_score": <0-100>,
  "strengths": ["ponto forte 1", "ponto forte 2", "ponto forte 3"],
  "gaps": ["lacuna 1", "lacuna 2"],
  "summary": "resumo de 2 frases sobre a chance de entrevista"
}}

Candidato: {resume_summary}

Vaga: {job_json}
"""

def _llm_score(job: dict, resume: dict) -> dict:
    prompt = LLM_PROMPT.format(
        resume_summary=(
            f"Nome: {resume.get('name')} | "
            f"Senioridade: {resume.get('seniority')} | "
            f"Skills: {', '.join(resume.get('skills', [])[:15])} | "
            f"Idiomas: {', '.join(resume.get('languages', []))}"
        ),
        job_json=json.dumps({
            "title":        job.get("title"),
            "company":      job.get("company"),
            "seniority":    job.get("seniority"),
            "requirements": job.get("requirements", []),
            "languages":    job.get("languages", []),
            "description":  job.get("description"),
        }, ensure_ascii=False)
    )

    response = client.models.generate_content(
        model=settings.ia_version,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.1),
    )

    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    return json.loads(raw)

def match(job: dict, resume: dict) -> dict:
    obj_score = _objective_score(job, resume)
    llm_data  = _llm_score(job, resume)

    # Score final: 70% objetivo + 30% LLM
    final_score = int(obj_score * 0.7 + llm_data["llm_score"] * 0.3)
    label = "Alta" if final_score >= 75 else "Média" if final_score >= 50 else "Baixa"

    return {
        "job":               job,
        "score":             final_score,
        "probability_label": label,
        "strengths":         llm_data.get("strengths", []),
        "gaps":              llm_data.get("gaps", []),
        "llm_summary":       llm_data.get("summary", ""),
    }