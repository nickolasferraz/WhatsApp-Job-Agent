# test_sprint2.py
import json
from pathlib import Path
from agent.query_builder import BooleanQueryBuilder
from agent.search_gateway import search_links
from agent.scraper import scrape_page

builder = BooleanQueryBuilder()
queries = builder.all_queries()

# Testa só o primeiro site (gupy) para não gastar créditos
first = queries[1]  # gupy.io
print(f"\n🔍 Query: {first['query']}\n")

links = search_links(first["query"])
print(f"✅ {len(links)} links encontrados:\n")
for l in links:
    print(f"  {l}")

# Scraping do primeiro link
if links:
    print(f"\n⏳ Fazendo scraping de: {links[0]}")
    scraped = scrape_page(links[0])

    # Salva resultado em output/
    Path("output").mkdir(exist_ok=True)
    with open("output/test_scrape.json", "w", encoding="utf-8") as f:
        json.dump(scraped, f, ensure_ascii=False, indent=2)

    print(f"✅ Scraping concluído!")
    print(f"   Primeiros 300 caracteres do texto:")
    print(f"   {scraped['text'][:300]}")