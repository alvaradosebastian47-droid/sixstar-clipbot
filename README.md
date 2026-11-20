# SIX STAR ClipBot

Bot que corre 24/7 en un VPS y produce y publica clips de streamers de GTA 6 para SIX STAR
(YouTube ES/EN, y TikTok/Instagram cuando se active), sin depender de las tareas de Claude.

## Qué hace cada 10 minutos (07:00–23:00, hora de Costa Rica)

1. **Radar**
   - Clips de GTA 6 en tendencia en Twitch, ordenados por velocidad (vistas por hora).
   - Picos de chat en los 3 streams más vistos de cada idioma. Pesan más las risas y el hype; el spam pesa menos.
2. **Grabación en vivo** (Streamlink): los 4 streams más grandes se graban con un buffer de 15 min.
   Cuando el chat explota, el momento ya está grabado y no hay que esperar al VOD.
3. **Corte**
   - Inicio y fin en pausas reales del habla (faster-whisper + VAD). Dura 12–30 s.
   - Empieza donde arranca la situación.
4. **Cámara**: OpenCV (YuNet) detecta la cara del streamer y arma el recorte de la webcam.
   Si no hay cara, el clip no se publica.
5. **Filtro de calidad**: la API de Claude ve 4 cuadros y la transcripción. Decide si se entiende solo y escribe:
   - el título ES/EN (quién + qué hacía + qué pasó, spoilers sin revelar);
   - la pregunta del primer comentario.
6. **Render v5** (`clipbot/rendk5.py`): el formato oficial de SIX STAR.
   - Cámara arriba, juego abajo, línea neón, título en cajas de color, marca discreta.
   - Subtítulos EN.
   - Export 1080x1920 a 60 fps, crf 12.
7. **Publicación**
   - YouTube con la API oficial: miniatura y primer comentario.
   - TikTok/IG con Upload-Post, cuando `tiktok: true`.
8. **Aviso por Telegram** con los links. Si TikTok sigue manual, llega también el archivo original
   como documento y el caption listo para copiar.

Las reglas fijas son: tope diario por canal, 25 min mínimo entre publicaciones, nunca el mismo
creador dos veces seguidas y nunca el mismo momento dos veces (SQLite).

## Instalación (VPS Ubuntu, 2 vCPU / 8 GB)

```bash
git clone https://github.com/alvaradosebastian47-droid/sixstar-clipbot /opt/clipbot
cd /opt/clipbot && bash deploy/install.sh
nano config.yaml                                   # claves
.venv/bin/python -m clipbot.main --once --dry-run  # prueba sin publicar
systemctl enable --now clipbot                     # arranca
journalctl -u clipbot -f                           # logs
```

## Claves que hacen falta (config.yaml)

| Clave | De dónde sale |
|---|---|
| `anthropic_api_key` | console.anthropic.com → API Keys (cargar ~$10) |
| `youtube.es` / `youtube.en` | `scripts/youtube_auth.py` (una vez por canal) |
| `uploadpost_api_key` | app.upload-post.com (plan Basic), perfiles `sixstar-es` y `sixstar-en` |
| `telegram_bot_token` / `telegram_chat_id` | @BotFather → nuevo bot; chat_id con @userinfobot |

## Ajustes rápidos

En `config.yaml`:
- `interval_minutes`: frecuencia del radar.
- `radar.min_velocity`: qué tan viral tiene que ser un clip.
- `judge.min_score`: qué tan estricto es el filtro.
- `accounts.*.tiktok`: activa la publicación automática en TikTok.
- `blocklist_creators`: creadores que no se usan (takedowns).
