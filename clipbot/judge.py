"""Filtro de calidad + títulos con la API de Claude (centavos por clip)."""
import base64
import json
import re

import anthropic

EMOJIS = "😭 💀 😂 🤣 🙏 🥀 😱 😳 🔥 👀"

PROMPT = """Eres el editor de SIX STAR, una página de clips de GTA 6 en YouTube Shorts y TikTok (español e inglés).
Te paso 4 cuadros de un clip candidato de un stream de {creator} ({platform}), la transcripción y el contexto.
Contexto: {context}
Transcripción: "{transcript}"

Decide si el clip merece publicarse y escribe los textos. Reglas:
- Debe ser un momento de GTA 6 que se entienda SOLO, sin haber visto el stream (situación + pico + reacción).
- Se debe ver la cara del streamer (reacción). Si es solo menú, carga, pantalla negra, sorteo, publicidad o charla sin juego: score bajo.
- Spoilers de historia están PERMITIDOS, pero el título NO revela el giro ni el final
  (ej. "La reacción de Speed a la misión final de GTA 6 😭"). Marca spoiler=true.
- Nada de desnudos, insultos racistas ni contenido que viole normas: score 0.
- Título = QUIÉN + QUÉ ESTABA HACIENDO + QUÉ PASÓ, en minúscula normal, 1-3 emojis SOLO de esta lista: {emojis}.
  Nunca "X juega GTA 6". Máximo 95 caracteres. Español latino natural / inglés natural de EE. UU.
- question_*: pregunta corta para el primer comentario que invite a responder.

Responde SOLO con JSON:
{{"score": 0-10, "reason": "...", "spoiler": true|false,
 "title_es": "...", "title_en": "...", "question_es": "...", "question_en": "..."}}"""


def judge(cfg, frames, transcript, creator, platform, context):
    client = anthropic.Anthropic(api_key=cfg["keys"]["anthropic_api_key"])
    content = []
    for p in frames:
        with open(p, "rb") as f:
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                         "data": base64.b64encode(f.read()).decode()}})
    content.append({"type": "text", "text": PROMPT.format(creator=creator, platform=platform, context=context,
                                                          transcript=transcript[:1500], emojis=EMOJIS)})
    msg = client.messages.create(model=cfg["judge"]["model"], max_tokens=600,
                                 messages=[{"role": "user", "content": content}])
    txt = "".join(b.text for b in msg.content if b.type == "text")
    m = re.search(r"\{.*\}", txt, re.S)
    out = json.loads(m.group(0)) if m else {"score": 0, "reason": "sin JSON"}
    # limpia emojis que no tenemos en PNG
    allowed = set(EMOJIS.split())
    for k in ("title_es", "title_en"):
        if k in out:
            out[k] = "".join(ch for ch in out[k] if not (ord(ch) > 0x1F000 and ch not in allowed)).strip()
    return out
