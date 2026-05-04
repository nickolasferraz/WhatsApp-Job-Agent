# agent/notifier.py
import httpx
from config.settings import settings

def _format_message(result: dict) -> str:
    job   = result["job"]
    score = result["score"]
    label = result["probability_label"]

    emoji = "🟢" if score >= 75 else "🟡" if score >= 50 else "🔴"

    strengths = "\n".join(f"  ✅ {s}" for s in result["strengths"][:3])
    gaps      = "\n".join(f"  ⚠️ {g}" for g in result["gaps"][:2])

    contact_line = ""
    contact = job.get("contact") or {}
    parts = []
    if contact.get("email"): parts.append(f"📧 {contact['email']}")
    if contact.get("phone"): parts.append(f"📱 {contact['phone']}")
    if parts:
        contact_line = "\n" + " | ".join(parts)

    return (
        f"{emoji} *{job.get('title')}* — {job.get('company')}\n"
        f"📍 {job.get('location') or 'N/A'} | 🏠 {job.get('work_mode') or 'N/A'}\n"
        f"🎯 Score: *{score}/100* ({label} chance)\n\n"
        f"💬 {result['llm_summary']}\n\n"
        f"*Pontos fortes:*\n{strengths}\n\n"
        f"*Gaps:*\n{gaps}"
        f"{contact_line}\n\n"
        f"🔗 {job.get('url')}"
    )

def send_to_group(result: dict) -> bool:
    import logging
    log = logging.getLogger(__name__)

    message = _format_message(result)
    url = f"{settings.evolution_api_url}/message/sendText/{settings.whatsapp_instance_name}"
    log.info(f"  🔗 POST {url}")
    try:
        resp = httpx.post(
            url,
            headers={"apikey": settings.authentication_api_key},
            json={
                "number":  settings.whatsapp_target,
                "text":   message,
                "options": {"delay": 1200, "presence": "composing"},
            },
            timeout=10,
        )
        log.info(f"  📡 Status: {resp.status_code}")
        log.info(f"  📄 Response: {resp.text[:300]}")
        # Evolution API retorna 201 Created no envio bem-sucedido
        return resp.status_code in (200, 201)
    except Exception as e:
        log.error(f"  ❌ Erro ao enviar WhatsApp: {type(e).__name__}: {e}")
        return False