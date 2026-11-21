"""REA's facts as defaults. A machine can override any of them in config.json at the repo root, or in the file named by
the env variable REA_BOARD_CONFIG. The file is a JSON object; a missing file is fine, a null value means the default, and
a value of the wrong type stops with a message. The repository is fixed: rea-board is for morluto/rea only.
Every getter reads the file when called.
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

CODE = os.path.dirname(os.path.abspath(__file__))
MAIN_SINCE_DAYS = 90
REPO = "morluto/rea"
LISTS = ("maintainers", "bot_names", "plan_authors", "unsorted_labels")
DEFAULTS = {
    "maintainers": ["morluto", "N0zoM1z0", "kaoru0822-kitauji", "baron"],
    "bot_names": ["coderabbitai", "github-actions", "chatgpt-codex-connector", "greptile-apps", "cubic-dev-ai"],
    "plan_authors": ["matbrgz"],
    "unsorted_labels": ["triage"],
    "data_dir": "data",
    "mirror": None,
    "main_since": None,
}


def path():
    return os.environ.get("REA_BOARD_CONFIG") or os.path.join(CODE, "config.json")


def settings():
    p = path()
    try:
        with open(p, encoding="utf-8") as fh:
            over = json.load(fh)
    except FileNotFoundError:
        return dict(DEFAULTS)
    except ValueError as e:
        sys.exit("conf: %s is not valid JSON (%s)" % (p, e))
    except OSError as e:
        sys.exit("conf: cannot read %s (%s)" % (p, e))
    if not isinstance(over, dict):
        sys.exit("conf: %s must hold a JSON object" % p)
    if "repo" in over:
        sys.exit("conf: %s sets repo, but rea-board is for %s only" % (p, REPO))
    s = dict(DEFAULTS, **{k: v for k, v in over.items() if v is not None})
    for k in LISTS:
        if not (isinstance(s[k], list) and all(isinstance(x, str) for x in s[k])):
            sys.exit("conf: %s in %s must be a list of names" % (k, p))
    for k in ("data_dir", "mirror", "main_since"):
        if s[k] is not None and not isinstance(s[k], str):
            sys.exit("conf: %s in %s must be text" % (k, p))
    if not s["data_dir"]:
        sys.exit("conf: data_dir in %s must not be empty" % p)
    if s["main_since"] and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s["main_since"]):
        sys.exit("conf: main_since in %s must be a date like 2026-01-31" % p)
    return s


def _path(p):
    return os.path.join(CODE, os.path.expanduser(p))


def repo():
    settings()
    return REPO


def maintainers():
    return list(settings()["maintainers"])


def bot_names():
    return list(settings()["bot_names"])


def plan_authors():
    return list(settings()["plan_authors"])


def unsorted_labels():
    return list(settings()["unsorted_labels"])


def data_dir():
    return _path(settings()["data_dir"])


def mirror():
    m = settings()["mirror"]
    return _path(m) if m else None


def main_since():
    return settings()["main_since"] or (datetime.now(timezone.utc) - timedelta(days=MAIN_SINCE_DAYS)).strftime("%Y-%m-%d")
