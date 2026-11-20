"""TikTok / Instagram vía Upload-Post (manda el archivo original)."""
import requests

API = "https://api.upload-post.com/api/upload"


def upload(api_key, user, path, title, platforms):
    with open(path, "rb") as f:
        data = [("title", title), ("user", user)] + [("platform[]", p) for p in platforms]
        r = requests.post(API, headers={"Authorization": "Apikey " + api_key},
                          files={"video": f}, data=data, timeout=600)
    r.raise_for_status()
    return r.json()
