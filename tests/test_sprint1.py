# test_sprint1.py
from config.settings import settings
from agent.query_builder import BooleanQueryBuilder

print("=== Configurações carregadas ===")
print(f"Sites alvo: {settings.target_sites}")
print(f"Score mínimo: {settings.min_score_to_notify}")
print(f"SerpAPI key: {'✅ OK' if settings.serpapi_key else '❌ não configurada'}")
print(f"Gemini key:  {'✅ OK' if settings.gemini_api_key else '❌ não configurada'}")

print("\n=== Queries Booleanas Geradas ===")
builder = BooleanQueryBuilder()
for item in builder.all_queries():
    print(f"\n🔍 {item['site']}")
    print(f"   {item['query']}")