# test_sprint3.py
import json
from pathlib import Path
from agent.resume_parser import parse_resume

print("⏳ Lendo e analisando o currículo...")

profile = parse_resume("config/CV - Carolina Soares Barbosa.pdf")

# Salva o perfil extraído para inspecionar
Path("output").mkdir(exist_ok=True)
with open("output/resume_profile.json", "w", encoding="utf-8") as f:
    json.dump(profile, f, ensure_ascii=False, indent=2)

print("\n✅ Currículo parseado com sucesso!")
print(f"\n👤 Nome:       {profile.get('name')}")
print(f"🎯 Cargos:     {profile.get('target_roles')}")
print(f"📊 Senioridade:{profile.get('seniority')}")
print(f"🛠  Skills:     {profile.get('skills')[:5]}...")
print(f"🌍 Idiomas:    {profile.get('languages')}")
print(f"📍 Locais:     {profile.get('locations_accepted')}")
print(f"\n💬 Resumo: {profile.get('summary')}")
print(f"\n💾 Perfil completo salvo em: output/resume_profile.json")