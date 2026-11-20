"""Twitch: streams y clips de una categoría, picos de chat del VOD, descargas."""
import json
import os
import shutil
import statistics
import subprocess
import tempfile
import time
import urllib.request
import concurrent.futures as cf
from datetime import datetime, timezone

CID = "kimne78kx3ncx6brgo4mv6wki5h1ko"
COMMENTS_HASH = "b70a3591ff0f4e0313d126c6a1502d79a1c02baebb288227c582044aa76adf6a"

HYPE = ("kekw", "omegalul", "lul", "lmao", "lmfao", "jaja", "😭", "💀", "no way", "pog", "clip", "w ", " w", "holy", "bro")
NOISE = ("!sorteo", "!giveaway", "raid", "1", "2", "3", "hola", "hello", "hi ", "yt is live", "subs")


def gql(payload, retries=3):
    for i in range(retries):
        try:
            req = urllib.request.Request("https://gql.twitch.tv/gql", data=json.dumps(payload).encode(),
                                         headers={"Client-Id": CID, "Content-Type": "application/json"})
            return json.load(urllib.request.urlopen(req, timeout=20))
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(2)


def category(game, n_streams=30, n_clips=50):
    q = '{ game(name:"%s"){ streams(first:%d){edges{node{broadcaster{login displayName} viewersCount language title}}} ' \
        'clips(first:%d, criteria:{period:LAST_DAY, sort:VIEWS_DESC}){edges{node{slug title viewCount createdAt ' \
        'durationSeconds language broadcaster{login displayName}}}}}}' % (game, n_streams, n_clips)
    g = gql({"query": q})["data"]["game"]
    streams = [e["node"] for e in g["streams"]["edges"]]
    clips = [e["node"] for e in g["clips"]["edges"]]
    now = datetime.now(timezone.utc)
    for c in clips:
        age = (now - datetime.fromisoformat(c["createdAt"].replace("Z", "+00:00"))).total_seconds() / 3600
        c["age_h"] = round(age, 2)
        c["velocity"] = round(c["viewCount"] / max(age, 0.25))
    return streams, clips


def latest_vod(login):
    q = '{user(login:"%s"){stream{id createdAt} videos(first:1,sort:TIME){edges{node{id title lengthSeconds createdAt}}}}}' % login
    u = gql({"query": q})["data"]["user"]
    if not u or not u.get("videos") or not u["videos"]["edges"]:  # canal sin VODs o con VODs ocultos
        return None
    v = u["videos"]["edges"][0]["node"]
    v["live"] = bool(u["stream"])
    return v


def _chat_rate(vid, off):
    try:
        d = gql([{"operationName": "VideoCommentsByOffsetOrCursor",
                  "variables": {"videoID": vid, "contentOffsetSeconds": off},
                  "extensions": {"persistedQuery": {"version": 1, "sha256Hash": COMMENTS_HASH}}}])[0]
        edges = d["data"]["video"]["comments"]["edges"]
        ts = [e["node"]["contentOffsetSeconds"] for e in edges]
        if len(ts) < 5:
            return off, 0.0, 0.0, []
        msgs = ["".join(f.get("text", "") for f in e["node"]["message"]["fragments"]).lower() for e in edges]
        span = max(1, max(ts) - min(ts))
        hype = sum(1 for m in msgs if any(h in m for h in HYPE))
        noise = sum(1 for m in msgs if m.strip() in NOISE or len(set(msgs)) < len(msgs) * 0.3)
        weight = 1 + hype / len(msgs) - 0.5 * noise / len(msgs)
        return off, len(ts) / span, weight, [m[:40] for m in msgs[:10]]
    except Exception:
        return off, 0.0, 0.0, []


def chat_peaks(login, minutes=30, step=15, min_x=3.0):
    """Picos de chat en los últimos `minutes` del VOD (en vivo o recién terminado)."""
    v = latest_vod(login)
    if not v:
        return None, []
    L = v["lengthSeconds"]
    # para la mediana se mira una ventana más larga (90 min) con paso mayor
    base_offs = list(range(max(0, L - 90 * 60), max(1, L - 5), 60))
    offs = list(range(max(0, int(L - minutes * 60)), max(1, int(L) - 5), step))
    with cf.ThreadPoolExecutor(8) as ex:
        base = list(ex.map(lambda o: _chat_rate(v["id"], o), base_offs))
        R = sorted(ex.map(lambda o: _chat_rate(v["id"], o), offs))
    rates = [r for _, r, _, _ in base if r > 0]
    med = statistics.median(rates) if rates else 0
    peaks = []
    for i, (o, r, w, m) in enumerate(R):
        score = r * w
        if med and score >= min_x * med and all(r >= R[j][1] for j in range(max(0, i - 2), min(len(R), i + 3))):
            peaks.append({"vod": v["id"], "t": o, "x": round(score / med, 1), "msgs": m,
                          "min_ago": round((L - o) / 60, 1), "live": v["live"], "vod_created": v["createdAt"]})
    peaks.sort(key=lambda p: -p["x"])
    return v, peaks[:5]


def download_clip(slug, out):
    subprocess.run(["yt-dlp", "-q", "--no-update", "-o", out, "https://clips.twitch.tv/" + slug], check=True, timeout=300)
    return out


def vodcut(vid, a, b, out):
    """Baja solo los segmentos .ts necesarios del VOD."""
    url = subprocess.run(["yt-dlp", "-q", "--no-update", "-g", "-f", "best[height<=1080]",
                          "https://www.twitch.tv/videos/" + str(vid)], capture_output=True, text=True,
                         timeout=120).stdout.strip().splitlines()[0]
    pl = urllib.request.urlopen(url, timeout=30).read().decode()
    base = url.rsplit("/", 1)[0] + "/"

    def absu(u):
        return u if u.startswith("http") else base + u

    # Twitch sirve VODs en fMP4 (#EXT-X-MAP init-N.mp4 + N.mp4) o, en VODs viejos, en .ts.
    # Los fragmentos fMP4 no se pueden abrir sueltos: hay que anteponer su segmento de inicio.
    t, segs, dur, first, init = 0.0, [], None, None, None
    for ln in pl.splitlines():
        if ln.startswith("#EXT-X-MAP:"):
            init = absu(ln.split('URI="', 1)[1].split('"', 1)[0])
        elif ln.startswith("#EXTINF:"):
            dur = float(ln[8:].split(",")[0])
        elif ln and not ln.startswith("#") and dur is not None:
            if t + dur > a and t < b:
                segs.append((init, absu(ln)))
                if first is None:
                    first = t
            t += dur
            dur = None
    if not segs:
        raise RuntimeError("VOD sin segmentos en ese rango")
    d = tempfile.mkdtemp()
    try:
        joined = os.path.join(d, "joined" + (".mp4" if segs[0][0] else ".ts"))
        last_init = None
        with open(joined, "wb") as f:
            for ini, s in segs:
                if ini and ini != last_init:  # el init solo se repite si cambia (p. ej. init-1.mp4)
                    f.write(urllib.request.urlopen(ini, timeout=30).read())
                    last_init = ini
                f.write(urllib.request.urlopen(s, timeout=30).read())
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", joined,
                        "-ss", str(a - first), "-t", str(b - a), "-c:v", "libx264", "-crf", "10",
                        "-preset", "veryfast", "-c:a", "aac", "-b:a", "320k", out], check=True)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return out
