"""SIX STAR ClipBot — ciclo principal.

python -m clipbot.main --once [--dry-run]   # una corrida
python -m clipbot.main --loop               # cada interval_minutes (servicio)
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime

from . import config as C, db, twitch, live, media, judge as J, notify
from .publish import youtube, uploadpost

LANGS = ("es", "en")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ---------------------------------------------------------------- radar
def candidates(cfg, streams, clips, lang):
    R = cfg["radar"]
    block = {b.lower() for b in cfg.get("blocklist_creators", [])}
    last = db.last_creator(lang)
    out = []
    # A) clips en tendencia (ya probados por la audiencia)
    for c in clips:
        if c["language"].lower() != lang or c["age_h"] > R["hard_max_age_hours"]:
            continue
        who = c["broadcaster"]["login"].lower()
        key = "clip:" + c["slug"]
        if who in block or who == last or c["velocity"] < R["min_velocity"] or db.is_used(key, lang):
            continue
        boost = 1.0 if c["age_h"] <= R["max_clip_age_hours"] else 0.4
        out.append({"kind": "clip", "key": key, "creator": who, "name": c["broadcaster"]["displayName"],
                    "score": c["velocity"] * boost, "clip": c, "context": f"Clip de Twitch '{c['title']}' "
                    f"con {c['viewCount']} vistas en {c['age_h']} h"})
    # B) picos de chat en los streams más grandes de ese idioma
    top = [s for s in streams if s["language"].lower() == lang][:R["live_streams_per_lang"]]
    for s in top:
        who = s["broadcaster"]["login"].lower()
        if who in block or who == last:
            continue
        try:
            vod, peaks = twitch.chat_peaks(who, R["chat_window_min"], 15, R["chat_peak_min_x"])
        except Exception as e:
            log("chat_peaks", who, e)
            continue
        for p in peaks:
            key = f"vod:{p['vod']}:{p['t'] // 45}"
            if db.is_used(key, lang):
                continue
            out.append({"kind": "peak", "key": key, "creator": who, "name": s["broadcaster"]["displayName"],
                        "score": p["x"] * 800, "peak": p, "stream_title": s["title"],
                        "context": f"Pico de chat x{p['x']} hace {p['min_ago']} min en el stream "
                        f"'{s['title']}'. Chat: {' | '.join(p['msgs'][:6])}"})
    out.sort(key=lambda x: -x["score"])
    return out


# ---------------------------------------------------------------- producción
def fetch_source(cfg, cand, wd):
    src = os.path.join(wd, "src.mp4")
    if cand["kind"] == "clip":
        twitch.download_clip(cand["clip"]["slug"], src)
        return src, media.loudest_moment(src)
    p = cand["peak"]
    a, b = max(0, p["t"] - 28), p["t"] + 10
    if cfg["live_capture"]["enabled"] and p["live"]:
        t0 = datetime.fromisoformat(p["vod_created"].replace("Z", "+00:00")).timestamp()
        if live.cut(cfg["workdir"], cand["creator"], t0 + a, t0 + b, src):
            return src, p["t"] - a
    twitch.vodcut(p["vod"], a, b, src)
    return src, p["t"] - a


def produce(cfg, cand, lang, wd, translated=False, dry=False):
    os.makedirs(wd, exist_ok=True)
    src, peak_t = fetch_source(cfg, cand, wd)
    info = media.probe(src)
    src_lang = "en" if (translated or lang == "en") else "es"
    ss, to, transcript = media.speech_bounds(src, peak_t, lang=src_lang)
    cam = media.find_facecam(src, info)
    if not cam:
        return None, {"score": 0, "reason": "no se detectó la cámara del streamer"}
    shots = media.frames(src, [ss + 0.5, max(ss, peak_t - 2), peak_t, max(ss, to - 1)], os.path.join(wd, "fr"))
    if dry and not cfg["keys"].get("anthropic_api_key"):
        # prueba local sin clave: no se llama a la API, se usa un veredicto fijo para probar el render
        log("dry-run sin anthropic_api_key: veredicto de prueba")
        v = {"score": 10, "reason": "prueba sin juez", "spoiler": False,
             "title_es": f"prueba de {cand['name']} en gta 6 🔥", "title_en": f"{cand['name']} gta 6 test clip 🔥",
             "question_es": "¿qué opinas?", "question_en": "thoughts?"}
    else:
        v = J.judge(cfg, shots, transcript, cand["name"], "Twitch", cand["context"])
    if v.get("score", 0) < cfg["judge"]["min_score"]:
        return None, v
    acc = cfg["accounts"][lang]
    game, shift = media.game_box(info, cam)
    rc = {"dir": wd, "src": src, "ss": ss, "to": to, "fps": info["fps"], "cam": cam, "game": game,
          "game_shift": shift, "name": cand["name"], "platform": "TWITCH", "user": cand["creator"],
          "accent": acc["accent"], "title": v["title_" + lang]}
    if acc["subs"] or src_lang == "en" and lang == "en":
        rc.update(subs=True, lang=src_lang)
    with open(os.path.join(wd, "cfg.json"), "w", encoding="utf-8") as f:
        json.dump(rc, f, ensure_ascii=False)
    subprocess.run([sys.executable, os.path.join(C.ROOT, "clipbot", "rendk5.py"), os.path.join(wd, "cfg.json")],
                   check=True, timeout=1800)
    out = os.path.join(wd, "clip_v5.mp4")
    thumb = media.frames(out, [min(peak_t - ss, to - ss - 0.5)], os.path.join(wd, "th"), width=1080)[0]
    return {"video": out, "thumb": thumb, "verdict": v}, v


# ---------------------------------------------------------------- publicación
def publish(cfg, lang, cand, res, dry):
    acc, keys = cfg["accounts"][lang], cfg["keys"]
    v = res["verdict"]
    title = v["title_" + lang]
    day = C.now(cfg).strftime("%Y-%m-%d")
    spoiler = "⚠️ Spoilers\n" if v.get("spoiler") else ""
    credit = f"Clip: {cand['name']} en twitch.tv/{cand['creator']}" if lang == "es" else \
        f"Clip: {cand['name']} on twitch.tv/{cand['creator']}"
    desc = f"{title}\n\n{spoiler}{credit}\n{acc['disclaimer']}\n\n#{cand['creator']} {acc['hashtags']}"
    caption = f"{title}\n{spoiler}Clip: twitch.tv/{cand['creator']}\n#{cand['creator']} {acc['hashtags']}"
    links = []
    L = cfg["limits"]
    if acc["youtube"] and db.posts_today(lang, "youtube", day) < L["youtube_per_day"] \
            and time.time() - db.last_post_ts(lang, "youtube") > L["min_minutes_between_posts"] * 60:
        if dry:
            links.append("youtube(dry)")
        else:
            try:
                url = youtube.upload(keys["youtube"][lang], res["video"], title, desc,
                                     ["GTA 6", "GTA VI", cand["name"], "GTA 6 clips"], res["thumb"],
                                     v.get("question_" + lang), lang)
                db.add_post(lang, "youtube", cand["creator"], title, url, cand["key"], day)
                links.append(url)
            except Exception as e:
                links.append(f"YouTube falló: {e}")
    plats = [p for p in ("tiktok", "instagram") if acc.get(p)]
    if plats and not dry:
        try:
            uploadpost.upload(keys["uploadpost_api_key"], acc["uploadpost_user"], res["video"], caption, plats)
            for p in plats:
                db.add_post(lang, p, cand["creator"], title, "upload-post", cand["key"], day)
            links.append("+".join(plats) + " ✓")
        except Exception as e:
            links.append(f"Upload-Post falló: {e}")
    return links, caption


# ---------------------------------------------------------------- ciclo
def run_once(cfg, dry=False):
    t = C.now(cfg)
    if C.is_quiet(cfg, t):
        log("horario de silencio")
        return
    streams, clips = twitch.category(cfg["game"])
    log(f"{len(streams)} streams · {len(clips)} clips en la categoría")
    if cfg["live_capture"]["enabled"]:
        top = [s["broadcaster"]["login"].lower() for s in streams[:cfg["live_capture"]["streams"]]]
        live.sync(cfg["workdir"], top, cfg["live_capture"]["buffer_minutes"])
    for lang in LANGS:
        cands = candidates(cfg, streams, clips, lang)
        translated = False
        if not cands and lang == "es":
            cands = candidates(cfg, streams, clips, "en")[:2]
            translated = True
        made = 0
        for cand in cands[:4]:
            if made >= cfg["limits"]["per_run_per_lang"]:
                break
            wd = os.path.join(cfg["workdir"], f"{t:%Y%m%d-%H%M}-{lang}-{cand['creator']}")
            log(lang, "probando", cand["kind"], cand["creator"], round(cand["score"]))
            try:
                res, v = produce(cfg, cand, lang, wd, translated, dry)
            except Exception:
                log(traceback.format_exc()[-800:])
                if not dry:
                    db.mark_used(cand["key"], lang, cand["creator"])
                continue
            if not dry:  # una prueba no debe "gastar" momentos que luego se publicarían
                db.mark_used(cand["key"], lang, cand["creator"])
            if not res:
                log("descartado:", v.get("reason"))
                continue
            links, caption = publish(cfg, lang, cand, res, dry)
            tag = "ES traducido" if translated else lang.upper()
            msg = (f"🎬 {tag} · {cand['name']}\n{res['verdict']['title_' + lang]}\n"
                   f"Fuente: {cand['context'][:160]}\n" + "\n".join(links) +
                   ("\n\n📲 Para TikTok (copia el caption):\n" + caption
                    if not cfg["accounts"][lang].get("tiktok") else ""))
            notify.send(cfg, msg, res["video"] if not cfg["accounts"][lang].get("tiktok") else None)
            made += 1
    # limpia carpetas de trabajo de más de 1 día
    for d in os.listdir(cfg["workdir"]):
        p = os.path.join(cfg["workdir"], d)
        if d != "live" and os.path.isdir(p) and time.time() - os.path.getmtime(p) > 86400:
            shutil.rmtree(p, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    # los logs y avisos llevan emojis: que nunca tumben la corrida por el encoding de la consola
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    cfg = C.load()
    if a.loop:
        while True:
            try:
                run_once(cfg, a.dry_run)
            except Exception:
                log(traceback.format_exc()[-1500:])
                notify.send(cfg, "⚠️ ClipBot error:\n" + traceback.format_exc()[-800:])
            time.sleep(cfg["interval_minutes"] * 60)
    else:
        run_once(cfg, a.dry_run)


if __name__ == "__main__":
    main()
