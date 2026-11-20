import os
import yaml
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")


def load(path=None):
    path = path or os.environ.get("CLIPBOT_CONFIG", os.path.join(ROOT, "config.yaml"))
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    os.makedirs(cfg["workdir"], exist_ok=True)
    return cfg


def now(cfg):
    return datetime.now(ZoneInfo(cfg["timezone"]))


def is_quiet(cfg, t=None):
    t = t or now(cfg)
    a, b = cfg["quiet_hours"]
    return t.hour >= a or t.hour < b
