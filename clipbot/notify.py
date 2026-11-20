"""Avisos por Telegram (texto y video para subir a mano)."""
import requests


def send(cfg, text, video=None):
    """video: se manda como DOCUMENTO para que Telegram no lo recomprima (listo para subir a mano)."""
    tok, chat = cfg["keys"].get("telegram_bot_token"), cfg["keys"].get("telegram_chat_id")
    if not tok or not chat:
        print("[telegram]", text)
        return
    base = f"https://api.telegram.org/bot{tok}/"
    try:
        if video:
            with open(video, "rb") as f:
                requests.post(base + "sendDocument", data={"chat_id": chat, "caption": text[:1000]},
                              files={"document": f}, timeout=300)
        else:
            requests.post(base + "sendMessage", data={"chat_id": chat, "text": text[:4000],
                                                      "disable_web_page_preview": True}, timeout=30)
    except Exception as e:
        print("[telegram error]", e)
