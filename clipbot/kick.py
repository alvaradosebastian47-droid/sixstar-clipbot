"""Kick: streams en vivo de GTA 6, clips, picos de chat y cortes de VOD.

Usa los endpoints web de kick.com (/api/v2/...) con curl_cffi (se hace pasar por Chrome para
que Cloudflare no lo bloquee). Devuelve streams y clips con la MISMA forma que twitch.py,
más "platform": "kick", para que el resto del bot los trate igual.
"""
import concurrent.futures as cf
import re
import statistics
import subprocess
import time
from datetime import datetime, timezone, timedelta

try:
    from curl_cffi import requests as _http
    _KW = {"impersonate": "chrome"}
except ImportError:  # sin curl_cffi funciona igual desde IPs no bloqueadas
    import requests as _http
    _KW = {"headers": {"User-Agent": "Mozilla/5.0"}}

from .twitch import HYPE, NOISE

GTA = "grand-theft-auto-vi"
EMOTE = re.compile(r"\[emote:\d+:([^\]]+)\]")


def get(path, retries=3):
    url = path if path.startswith("http") else "https://kick.com" + path
    last = None
    for _ in range(retries):
        try:
            r = _http.get(url, timeout=20, **_KW)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return None
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = str(e)[:80]
        time.sleep(2)
    raise RuntimeError(f"Kick {url}: {last}")


def _ts(s):
    """'2026-11-20 21:43:52' o '2026-11-20T21:43:52Z' (UTC) -> datetime UTC."""
    s = s.replace("Z", "").replace(" ", "T").split(".")[0].split("+")[0]
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _is_gta(cat):
    return (cat or {}).get("slug") == GTA or "Grand Theft Auto VI" in ((cat or {}).get("name") or "")


def live_gta(slugs):
    """Streams en vivo jugando GTA 6 de los canales `slugs`, ordenados por espectadores."""
    def one(s):
        try:
            j = get(f"/api/v2/channels/{s}")
        except Exception:
            return None
        ls = (j or {}).get("livestream")
        if not ls or not any(_is_gta(c) for c in ls.get("categories") or []):
            return None
        return {"broadcaster": {"login": j["slug"].lower(),
                                "displayName": (j.get("user") or {}).get("username") or j["slug"]},
                "viewersCount": int(ls.get("viewer_count") or 0), "language": ls.get("lang_iso") or "",
                "title": ls.get("session_title") or "", "platform": "kick", "kick_id": j["id"]}
    with cf.ThreadPoolExecutor(8) as ex:
        out = [x for x in ex.map(one, slugs) if x]
    return sorted(out, key=lambda s: -s["viewersCount"])


def clips(slugs):
    """Clips de GTA 6 de las últimas 24 h de los canales `slugs` (forma de twitch.category)."""
    now = datetime.now(timezone.utc)

    def one(s):
        try:
            return ((get(f"/api/v2/channels/{s}/clips?sort=view&time=day") or {}).get("clips") or [], s)
        except Exception:
            return [], s
    out = []
    with cf.ThreadPoolExecutor(8) as ex:
        for lst, s in ex.map(one, slugs):
            for c in lst:
                if not _is_gta(c.get("category")) or not (c.get("clip_url") or c.get("video_url")):
                    continue
                age = (now - _ts(c["created_at"])).total_seconds() / 3600
                views = int(c.get("views") or c.get("view_count") or 0)
                ch = c.get("channel") or {}
                out.append({"slug": c["id"], "title": c.get("title") or "", "viewCount": views,
                            "createdAt": c["created_at"], "durationSeconds": c.get("duration"), "language": "",
                            "platform": "kick", "clip_url": c.get("clip_url") or c.get("video_url"),
                            "broadcaster": {"login": (ch.get("slug") or s).lower(),
                                            "displayName": ch.get("username") or ch.get("slug") or s},
                            "age_h": round(age, 2), "velocity": round(views / max(age, 0.25))})
    return out


def download_clip(clip_url, out):
    """Los clips de Kick son HLS (m3u8): se bajan con ffmpeg sin recomprimir."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", clip_url, "-c", "copy", "-bsf:a", "aac_adtstoasc", out],
                   check=True, timeout=300)
    return out


def latest_vod(slug):
    vids = get(f"/api/v2/channels/{slug}/videos") or []
    if not vids or not vids[0].get("source"):
        return None
    v = vids[0]
    start = _ts(v["start_time"])
    live = bool(v.get("is_live"))
    length = (datetime.now(timezone.utc) - start).total_seconds() if live else (v.get("duration") or 0) / 1000
    return {"id": (v.get("video") or {}).get("uuid") or str(v.get("id")), "source": v["source"], "live": live,
            "start": start, "lengthSeconds": int(length)}


def _chat_rate(cid, t):
    """Kick devuelve los mensajes de una ventana de ~5 s desde `t` (máx. 25): mensajes por segundo."""
    try:
        j = get(f"/api/v2/channels/{cid}/messages?start_time={t.strftime('%Y-%m-%dT%H:%M:%S.000Z')}")
        ms = ((j or {}).get("data") or {}).get("messages") or []
        if len(ms) < 3:
            return 0.0, 0.0, []
        ts = [_ts(m["created_at"]).timestamp() for m in ms]
        span = max(ts) - min(ts) + 1  # segundos enteros: 25 mensajes en el mismo segundo = 25/s
        msgs = [EMOTE.sub(r"\1", (m.get("content") or "")).lower() for m in ms]
        hype = sum(1 for m in msgs if any(h in m for h in HYPE))
        noise = sum(1 for m in msgs if m.strip() in NOISE or len(set(msgs)) < len(msgs) * 0.3)
        return len(ms) / span, 1 + hype / len(msgs) - 0.5 * noise / len(msgs), [m[:40] for m in msgs[:10]]
    except Exception:
        return 0.0, 0.0, []


def chat_peaks(slug, minutes=30, step=15, min_x=3.0):
    """Picos de chat en los últimos `minutes` del stream (mismo formato que twitch.chat_peaks)."""
    ch = get(f"/api/v2/channels/{slug}")
    v = latest_vod(slug)
    if not ch or not v:
        return None, []
    cid, L, t0 = ch["id"], v["lengthSeconds"], v["start"]
    base_offs = list(range(max(0, L - 90 * 60), max(1, L - 5), 60))
    offs = list(range(max(0, int(L - minutes * 60)), max(1, int(L) - 5), step))
    rate = lambda o: (o, *_chat_rate(cid, t0 + timedelta(seconds=o)))
    with cf.ThreadPoolExecutor(8) as ex:
        base = list(ex.map(rate, base_offs))
        R = sorted(ex.map(rate, offs))
    rates = [r for _, r, _, _ in base if r > 0]
    med = statistics.median(rates) if rates else 0
    peaks = []
    for i, (o, r, w, m) in enumerate(R):
        score = r * w
        if med and score >= min_x * med and all(r >= R[j][1] for j in range(max(0, i - 2), min(len(R), i + 3))):
            peaks.append({"vod": v["id"], "t": o, "x": round(score / med, 1), "msgs": m, "platform": "kick",
                          "min_ago": round((L - o) / 60, 1), "live": v["live"], "source": v["source"],
                          "vod_created": t0.strftime("%Y-%m-%dT%H:%M:%SZ")})
    peaks.sort(key=lambda p: -p["x"])
    return v, peaks[:5]


def vodcut(source, a, b, out):
    """Corta [a, b] segundos del VOD (m3u8) de Kick."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(a), "-i", source, "-t", str(b - a),
                    "-c:v", "libx264", "-crf", "10", "-preset", "veryfast", "-c:a", "aac", "-b:a", "320k", out],
                   check=True, timeout=600)
    return out
