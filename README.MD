# 🤖 WhatsApp Job Agent

Agente automatizado que monitora grupos de WhatsApp, identifica vagas de emprego e encaminha oportunidades relevantes automaticamente.

---

## 🚀 Tecnologias

| Tecnologia | Função |
|---|---|
| Python | Agente principal |
| Evolution API v2.2.3 | Gateway WhatsApp |
| PostgreSQL 15 | Banco de dados |
| Redis 7 | Cache local |
| Docker & Docker Compose | Containerização |
| GitHub Actions | CI/CD automático |

---

## Como o WhatsApp Job Agent Funciona
1. 📥 Recebimento de Mensagens
A Evolution API fica conectada ao WhatsApp e age como um gateway. Toda mensagem recebida nos grupos monitorados é capturada via webhook e enviada para o agente Python.

2. 🧠 Processamento pelo Agente
O agente Python recebe o payload da mensagem e verifica:

Se a mensagem vem de um grupo monitorado

Se o conteúdo tem palavras-chave de vaga (ex: "contratando", "vaga", "CLT", "PJ", "salário")

Se a vaga é relevante para o perfil configurado

3. 💾 Armazenamento
Vagas identificadas são salvas no PostgreSQL para evitar duplicatas e manter histórico

O Redis cuida do cache local, evitando reprocessar mensagens já vistas

4. 📤 Envio Automático
Se a vaga passar nos filtros, o agente usa a Evolution API para encaminhar automaticamente a mensagem para:

Um contato específico

Um grupo de destino

Ou uma lista de contatos cadastrados


