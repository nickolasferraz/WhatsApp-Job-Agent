# test_sprint5.py
import json
from agent.notifier import send_to_group

# Carrega o resultado do match já feito na Sprint 4
with open("output/test_match.json", encoding="utf-8") as f:
    result = json.load(f)

print("⏳ Enviando vaga para o grupo de WhatsApp...")
success = send_to_group(result)

if success:
    print("✅ Mensagem enviada com sucesso!")
else:
    print("❌ Falha no envio — verifique o .env e se o Docker está rodando")