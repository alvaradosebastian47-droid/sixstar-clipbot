"""Subida directa a YouTube con la API oficial (archivo original, sin recompresión intermedia)."""
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.force-ssl"]


def _client(k):
    creds = Credentials(None, refresh_token=k["refresh_token"], client_id=k["client_id"],
                        client_secret=k["client_secret"], token_uri="https://oauth2.googleapis.com/token",
                        scopes=SCOPES)
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload(keys, path, title, description, tags, thumb=None, first_comment=None, lang="es"):
    yt = _client(keys)
    body = {"snippet": {"title": title[:100], "description": description, "tags": tags, "categoryId": "20",
                        "defaultLanguage": lang, "defaultAudioLanguage": lang},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(path, chunksize=8 * 1024 * 1024, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid = resp["id"]
    if thumb:
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(thumb)).execute()
        except Exception:
            pass  # los Shorts a veces no aceptan miniatura personalizada
    if first_comment:
        try:
            yt.commentThreads().insert(part="snippet", body={"snippet": {"videoId": vid, "topLevelComment": {
                "snippet": {"textOriginal": first_comment}}}}).execute()
        except Exception:
            pass
    return "https://youtube.com/shorts/" + vid
