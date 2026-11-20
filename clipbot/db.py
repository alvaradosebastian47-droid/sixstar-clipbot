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
    return c


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
