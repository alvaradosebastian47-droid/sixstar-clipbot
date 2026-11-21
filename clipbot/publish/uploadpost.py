"""TikTok / Instagram vía Upload-Post (manda el archivo original).

API: POST https://api.upload-post.com/api/upload (multipart), header "Authorization: Apikey <clave>".
Los clips del bot duran < 60 s, así que la respuesta es síncrona y trae el resultado por plataforma.
"""
import uuid

import requests

API = "https://api.upload-post.com/api/upload"


class UploadPostError(RuntimeError):
    pass


def upload(api_key, user, path, title, platforms, first_comment=None):
    """Sube el video a `platforms` (p. ej. ["tiktok"]) del perfil `user`.

    Devuelve {plataforma: url_o_"ok"}. Lanza UploadPostError si alguna plataforma falló.
    """
    data = [("user", user), ("title", title)] + [("platform[]", p) for p in platforms]
    if first_comment:
        data.append(("first_comment", first_comment))
    # Idempotency-Key: si se corta la conexión y se reintenta, Upload-Post no publica dos veces
    headers = {"Authorization": "Apikey " + api_key, "Idempotency-Key": uuid.uuid4().hex}
    with open(path, "rb") as f:
        r = requests.post(API, headers=headers, files={"video": f}, data=data, timeout=600)
    try:
        j = r.json()
    except ValueError:
        j = {}
    if r.status_code >= 400 or not j.get("success", False):
        raise UploadPostError(f"HTTP {r.status_code}: {j.get('message') or j.get('error') or r.text[:200]}")
    res = j.get("results") or {}
    out, errs = {}, []
    for p in platforms:
        pr = res.get(p) or {}
        if pr.get("success") or pr.get("status") in ("completed", "processing", "queued"):
            out[p] = pr.get("url") or "ok"
        elif pr:
            errs.append(f"{p}: {pr.get('error') or pr.get('skip_reason') or pr}")
        else:
            out[p] = "ok"  # respuesta sin detalle por plataforma: se da por aceptada
    if errs:
        raise UploadPostError("; ".join(errs))
    return out
