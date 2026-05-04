# test_sprint4.py
import json
from pathlib import Path
from agent.scraper import scrape_page
from agent.extractor import extract_job
from agent.matcher import match

# Carrega o perfil do currículo já extraído na Sprint 3
with open("output/resume_profile.json", encoding="utf-8") as f:
    resume = json.load(f)

# URL de teste — uma vaga real do Gupy
TEST_URL = "https://grupoboticario.gupy.io/jobs/11024402"

print(f"⏳ Scraping: {TEST_URL}")
scraped = scrape_page(TEST_URL)

print("⏳ Extraindo dados da vaga via Gemini...")
job = extract_job(scraped)

if not job:
    print("❌ Falha na extração")
    exit()

print(f"\n✅ Vaga extraída:")
print(f"   Título:    {job.get('title')}")
print(f"   Empresa:   {job.get('company')}")
print(f"   Local:     {job.get('location')} | {job.get('work_mode')}")
print(f"   Requisitos:{job.get('requirements', [])[:3]}")

print("\n⏳ Calculando score de compatibilidade...")
result = match(job, resume)

print(f"\n{'='*45}")
print(f"🎯 SCORE FINAL: {result['score']}/100 — {result['probability_label']} chance")
print(f"{'='*45}")
print(f"\n💬 {result['llm_summary']}")
print(f"\n✅ Pontos fortes:")
for s in result["strengths"]:
    print(f"   ✅ {s}")
print(f"\n⚠️  Gaps:")
for g in result["gaps"]:
    print(f"   ⚠️  {g}")

# Salva resultado completo
Path("output").mkdir(exist_ok=True)
with open("output/test_match.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"\n💾 Resultado salvo em: output/test_match.json")