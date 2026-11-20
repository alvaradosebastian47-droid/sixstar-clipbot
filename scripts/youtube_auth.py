"""Autoriza un canal de YouTube para el bot (una sola vez por canal).

1. Pon client_secret.json (Google Cloud → OAuth, tipo "App de escritorio") en la carpeta del proyecto.
2. Corre:  .venv\\Scripts\\python scripts\\youtube_auth.py es     (o "en" para el canal en inglés)
3. Se abre el navegador: entra con la cuenta de Google y elige el canal correcto.
4. El permiso se guarda solo en config.yaml (keys.youtube.es / .en). No imprime ninguna clave.
"""
import os
import re
import sys

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.force-ssl"]

lang = (sys.argv[1] if len(sys.argv) > 1 else "").lower()
if lang not in ("es", "en"):
    sys.exit("Uso: python scripts/youtube_auth.py es|en")
secret = os.path.join(ROOT, "client_secret.json")
cfg_path = os.path.join(ROOT, "config.yaml")
if not os.path.exists(secret):
    sys.exit("Falta client_secret.json en " + ROOT)

flow = InstalledAppFlow.from_client_secrets_file(secret, SCOPES)
creds = flow.run_local_server(port=0, prompt="consent", access_type="offline",
                              authorization_prompt_message="Se abrió el navegador: entra con la cuenta del canal " + lang.upper(),
                              success_message="Listo, ya puedes cerrar esta pestaña.")
if not creds.refresh_token:
    sys.exit("Google no devolvió refresh_token; vuelve a intentarlo.")

yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
items = yt.channels().list(part="snippet", mine=True).execute().get("items", [])
name = items[0]["snippet"]["title"] if items else "(esta cuenta no tiene canal)"

with open(cfg_path, encoding="utf-8") as f:
    txt = f.read()
line = f'    {lang}: {{client_id: "{creds.client_id}", client_secret: "{creds.client_secret}", ' \
       f'refresh_token: "{creds.refresh_token}"}}'
new, n = re.subn(rf"^    {lang}: \{{client_id:.*\}}$", line, txt, flags=re.M)
if n != 1:
    sys.exit(f"No encontré la línea keys.youtube.{lang} en config.yaml")
with open(cfg_path, "w", encoding="utf-8") as f:
    f.write(new)
print(f"OK: canal {lang.upper()} autorizado -> «{name}». Guardado en config.yaml.")
