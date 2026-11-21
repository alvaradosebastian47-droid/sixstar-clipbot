"""SQLite: momentos usados, publicaciones y conteos diarios."""
import os
import sqlite3
import time
from .config import ROOT

DB = os.environ.get("CLIPBOT_DB", os.path.join(ROOT, "clipbot.db"))


def conn():
    c = sqlite3.connect(DB)
    c.execute("""create table if not exists used(
        key text, lang text, creator text, ts real, primary key(key, lang))""")
    c.execute("""create table if not exists posts(
        id integer primary key, lang text, platform text, creator text, title text,
        url text, source text, ts real, day text)""")
    c.execute("""create table if not exists events(day text, lang text, kind text, ts real)""")
    c.execute("""create table if not exists stats(
        day text, lang text, subs integer, views integer, videos integer, primary key(day, lang))""")
    c.execute("""create table if not exists meta(k text primary key, v text)""")
    return c


# ---- reporte: eventos del día, fotos diarias de los canales y estado
def event(day, lang, kind):
    """kind: probado | descartado | error | publicado | fallo_publicacion"""
    with conn() as c:
        c.execute("insert into events values(?,?,?,?)", (day, lang, kind, time.time()))


def events_count(day, lang):
    with conn() as c:
        return dict(c.execute("select kind, count(*) from events where day=? and lang=? group by kind",
                              (day, lang)).fetchall())


def save_stats(day, lang, subs, views, videos):
    with conn() as c:
        c.execute("insert or replace into stats values(?,?,?,?,?)", (day, lang, subs, views, videos))


def stats_before(day, lang):
    """Última foto del canal anterior a `day` (para calcular cuánto creció)."""
    with conn() as c:
        return c.execute("select subs, views, videos from stats where lang=? and day<? order by day desc limit 1",
                         (lang, day)).fetchone()


def posts_since(lang, ts):
    with conn() as c:
        return c.execute("select creator, title, url from posts where lang=? and platform='youtube' and ts>=? "
                         "and url like 'https://youtube.com/shorts/%'", (lang, ts)).fetchall()


def meta_get(k):
    with conn() as c:
        r = c.execute("select v from meta where k=?", (k,)).fetchone()
        return r[0] if r else None


def meta_set(k, v):
    with conn() as c:
        c.execute("insert or replace into meta values(?,?)", (k, v))


def is_used(key, lang):
    with conn() as c:
        return c.execute("select 1 from used where key=? and lang=?", (key, lang)).fetchone() is not None


def mark_used(key, lang, creator):
    with conn() as c:
        c.execute("insert or replace into used values(?,?,?,?)", (key, lang, creator.lower(), time.time()))


def last_creator(lang):
    with conn() as c:
        r = c.execute("select creator from used where lang=? order by ts desc limit 1", (lang,)).fetchone()
        return r[0] if r else None


def add_post(lang, platform, creator, title, url, source, day):
    with conn() as c:
        c.execute("insert into posts(lang,platform,creator,title,url,source,ts,day) values(?,?,?,?,?,?,?,?)",
                  (lang, platform, creator, title, url, source, time.time(), day))


def posts_today(lang, platform, day):
    with conn() as c:
        return c.execute("select count(*) from posts where lang=? and platform=? and day=?",
                         (lang, platform, day)).fetchone()[0]


def last_post_ts(lang, platform):
    with conn() as c:
        r = c.execute("select max(ts) from posts where lang=? and platform=?", (lang, platform)).fetchone()
        return r[0] or 0
