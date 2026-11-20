"""Saca el refresh_token de YouTube (una sola vez por canal).

1. En Google Cloud Console crea un proyecto, activa "YouTube Data API v3" y crea credenciales
   OAuth de tipo "App de escritorio". Descarga el JSON como client_secret.json junto a este script.
2. Corre en tu PC:  python youtube_auth.py
3. Se abre el navegador: entra con la cuenta de Google del canal (elige el canal ES o EN).
4. Copia client_id, client_secret y refresh_token que imprime a config.yaml (keys.youtube.es / .en).
"""
import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.force-ssl"]
flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
print(json.dumps({"client_id": creds.client_id, "client_secret": creds.client_secret,
                  "refresh_token": creds.refresh_token}, indent=2))
