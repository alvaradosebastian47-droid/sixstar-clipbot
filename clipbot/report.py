"""Reporte diario por Telegram: crecimiento de los canales y cómo van los clips.

python -m clipbot.report          # manda el reporte ahora (no espera la hora)
python -m clipbot.report --print  # solo lo muestra en pantalla
"""
import sys
import time

from . import config as C, db, notify
from .publish import youtube

LANGS = ("es", "en")
NAMES = {"es": "🇪🇸 ES", "en": "🇺🇸 EN"}


def _fmt(n):
    return f"{n:,}".replace(",", ".")


def _delta(n):
    return ("+" if n >= 0 else "") + _fmt(n)


def channel(cfg, lang):
    yt = youtube._client(cfg["keys"]["youtube"][lang])
    it = yt.channels().list(part="snippet,statistics", mine=True).execute()["items"][0]
    s = it["statistics"]
    return yt, it["snippet"]["title"], int(s.get("subscriberCount", 0)), int(s.get("viewCount", 0)), \
        int(s.get("videoCount", 0))


def top_videos(yt, rows, n=3):
    """Los Shorts publicados por el bot con más vistas (de los que pasan en `rows`)."""
    ids = {u.rsplit("/", 1)[1]: (who, title) for who, title, u in rows}
    out = []
    keys = list(ids)
    for i in range(0, len(keys), 50):
        r = yt.videos().list(part="statistics", id=",".join(keys[i:i + 50])).execute()
        for v in r.get("items", []):
            st = v["statistics"]
            out.append((int(st.get("viewCount", 0)), int(st.get("likeCount", 0)), v["id"], *ids[v["id"]]))
    return sorted(out, reverse=True)[:n]


def build(cfg):
    day = C.now(cfg).strftime("%Y-%m-%d")
    lines = [f"📊 Reporte SIX STAR · {day}"]
    for lang in LANGS:
        if not cfg["accounts"][lang].get("youtube"):
            continue
        lines.append("")
        try:
            yt, title, subs, views, videos = channel(cfg, lang)
        except Exception as e:
            lines.append(f"{NAMES[lang]}: no pude leer el canal ({str(e)[:120]})")
            continue
        prev = db.stats_before(day, lang)
        db.save_stats(day, lang, subs, views, videos)
        d_subs = f" ({_delta(subs - prev[0])} hoy)" if prev else ""
        d_views = f" ({_delta(views - prev[1])} hoy)" if prev else ""
        lines.append(f"{NAMES[lang]} · {title}")
        lines.append(f"👥 {_fmt(subs)} suscriptores{d_subs}")
        lines.append(f"👁 {_fmt(views)} vistas totales{d_views}")
        ev = db.events_count(day, lang)
        lines.append(f"🎬 Hoy: {ev.get('probado', 0)} momentos revisados · {ev.get('descartado', 0)} descartados · "
                     f"{ev.get('publicado', 0)} en YouTube"
                     + (f" · {ev.get('publicado_tiktok', 0)} en TikTok" if cfg["accounts"][lang].get("tiktok") else "")
                     + (f" · {ev.get('publicado_instagram', 0)} en Instagram" if cfg["accounts"][lang].get("instagram") else "")
                     + (f" · ⚠️ {ev.get('fallo_publicacion', 0)} subidas fallidas" if ev.get("fallo_publicacion") else "")
                     + (f" · {ev.get('error', 0)} errores" if ev.get("error") else ""))
        rows = db.posts_since(lang, time.time() - 7 * 86400)
        if rows:
            try:
                top = top_videos(yt, rows)
                lines.append("🏆 Top de la semana:")
                for i, (v, likes, vid, who, t) in enumerate(top, 1):
                    lines.append(f"{i}. {_fmt(v)} vistas · {_fmt(likes)} likes · {who}\n   {t[:70]}\n   youtube.com/shorts/{vid}")
            except Exception as e:
                lines.append(f"(no pude leer las vistas de los Shorts: {str(e)[:100]})")
        else:
            lines.append("🏆 Todavía no hay Shorts del bot esta semana.")
    return "\n".join(lines)


def maybe_send(cfg):
    """Manda el reporte una vez al día, a partir de report_hour (hora de Costa Rica)."""
    t = C.now(cfg)
    day = t.strftime("%Y-%m-%d")
    if t.hour < cfg.get("report_hour", 22) or db.meta_get("last_report") == day:
        return
    db.meta_set("last_report", day)
    notify.send(cfg, build(cfg))


if __name__ == "__main__":
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    cfg = C.load()
    txt = build(cfg)
    if "--print" in sys.argv:
        print(txt)
    else:
        notify.send(cfg, txt)
