"""REA's facts as defaults. A machine can override any of them in config.json at the repo root, or in the file named by
the env variable REA_BOARD_CONFIG. The file is a JSON object; a missing file is fine, a null value means the default.
Every getter reads the file when called.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

CODE = os.path.dirname(os.path.abspath(__file__))
MAIN_SINCE_DAYS = 90
DEFAULTS = {
    "repo": "morluto/rea",
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
    return dict(DEFAULTS, **{k: v for k, v in over.items() if v is not None})


def _path(p):
    return os.path.join(CODE, os.path.expanduser(p))


def repo():
    return settings()["repo"]


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
