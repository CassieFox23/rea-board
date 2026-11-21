#!/usr/bin/env python3
"""Count the open pile from board.json: pull requests by whose move it is, issues by the sort pull.py stored.

usage: lanes.py --board BOARD.json [--append STATS.tsv]

Prints the counts. With --append, adds one row to STATS.tsv: the board's fetchedAt, then a column for each lane key,
pull requests first. A fetchedAt already in the file gets no second row, and a file whose header is not the current
columns is left alone and the script stops.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conf  # noqa: E402

DEAD_DAYS = 14
FRONT_DAYS = 3
PR_LANES = ("flow", "front", "decide", "landed", "author", "dead")
ISSUE_LANES = ("plan", "inflight", "landed", "ask", "machine", "sample", "bug", "unsorted")
LABELS = {
    "flow": "Maintainers' own and bots",
    "front": "Green, under %d days old" % FRONT_DAYS,
    "decide": "Green and waiting %d days or more" % FRONT_DAYS,
    "landed": "Fix already on main",
    "author": "Waiting on the author",
    "dead": "No push for %d days or more" % DEAD_DAYS,
    "plan": "Maintainers' plan",
    "inflight": "A pull request is open for it",
    "ask": "A feature, design or question",
    "machine": "Needs a Mac, Windows, a device or a paid tool",
    "sample": "Needs a sample file",
    "bug": "A bug report",
    "unsorted": "Not sorted yet",
}
PR_WHY = {
    "flow": "a maintainer or a bot wrote it",
    "landed": "a commit on main mentions it",
    "dead": "a draft, conflicting or red, with no push for %d days or more" % DEAD_DAYS,
    "author": "a draft, conflicting or red, or CI is not green",
    "front": "CI passing, opened under %d days ago" % FRONT_DAYS,
    "decide": "CI passing, opened %d or more days ago" % FRONT_DAYS,
}
COLUMNS = ["taken"] + ["pr_" + k for k in PR_LANES] + ["issue_" + k for k in ISSUE_LANES]
STUCK_CI = ("FAILURE", "ERROR")


def when(s):
    """s as an aware time, or None when it is empty or not an ISO time. A time with no zone counts as UTC."""
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def names(logins):
    return {str(n).lower() for n in logins}


def pr_lane(item, now, maintainers, bots):
    """The lane key of one PR, first match wins: flow (a maintainer or a bot wrote it), landed (named in main), then, for a
    PR that is a draft, conflicting or red, dead (last push DEAD_DAYS or more back, pushedAt else updatedAt) or author; any
    other PR whose CI is not green is author; a green one is front (created under FRONT_DAYS back) or decide. A time that is
    missing or does not parse makes no claim: not dead, not front."""
    if str(item.get("author") or "").lower() in names(maintainers) | names(bots):
        return "flow"
    if item.get("namedInMain"):
        return "landed"
    stuck = bool(item.get("isDraft")) or item.get("mergeable") == "CONFLICTING" or item.get("ci") in STUCK_CI
    if stuck:
        pushed = when(item.get("pushedAt") or item.get("updatedAt"))
        return "dead" if pushed and now - pushed >= timedelta(days=DEAD_DAYS) else "author"
    if item.get("ci") != "SUCCESS":
        return "author"
    created = when(item.get("createdAt"))
    return "front" if created and now - created < timedelta(days=FRONT_DAYS) else "decide"


def count(items, now, maintainers, bots):
    """{"prs": {...}, "issues": {...}}: the items in each lane, a zero for an empty lane, in PR_LANES and ISSUE_LANES order.
    A PR's lane comes from pr_lane. An issue's comes from the sort pull.py stored; one with no sort, or a sort that is not
    in ISSUE_LANES, counts as unsorted."""
    out = {"prs": dict.fromkeys(PR_LANES, 0), "issues": dict.fromkeys(ISSUE_LANES, 0)}
    for i in items:
        if i.get("kind") == "PR":
            out["prs"][pr_lane(i, now, maintainers, bots)] += 1
        elif str(i.get("kind") or "").lower() == "issue":
            out["issues"][i.get("sort") if i.get("sort") in ISSUE_LANES else "unsorted"] += 1
    return out


def config():
    """(maintainers, bots) from config."""
    return conf.maintainers(), conf.bot_names()


def report(counts):
    """The counts as printable lines: a total for pull requests and for issues, then a line for each lane."""
    out = []
    for title, keys, got in (("Pull requests", PR_LANES, counts["prs"]), ("Issues", ISSUE_LANES, counts["issues"])):
        out.append("%s: %d" % (title, sum(got.values())))
        out += ["  %s: %d" % (LABELS[k], got[k]) for k in keys]
    return out


def row(taken, counts):
    return [taken] + [str(counts["prs"][k]) for k in PR_LANES] + [str(counts["issues"][k]) for k in ISSUE_LANES]


def append_row(path, taken, counts):
    """Add the row for taken to the tsv at path, with a header when the file is new or empty; False when taken is already there.
    A file with any other header stops the script."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        text = ""
    if text.strip() and text.splitlines()[0] != "\t".join(COLUMNS):
        sys.exit("lanes: %s has other columns than this version writes; move it aside and run again" % path)
    if taken in {l.split("\t")[0] for l in text.splitlines()}:
        return False
    with open(path, "a", encoding="utf-8") as fh:
        if not text.strip():
            fh.write("\t".join(COLUMNS) + "\n")
        elif not text.endswith("\n"):
            fh.write("\n")
        fh.write("\t".join(row(taken, counts)) + "\n")
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description="Count the open pile from board.json.")
    ap.add_argument("--board", required=True)
    ap.add_argument("--append")
    a = ap.parse_args(argv)
    try:
        with open(a.board, encoding="utf-8") as fh:
            board = json.load(fh)
    except (OSError, ValueError) as ex:
        sys.exit("lanes: cannot read %s (%s)" % (a.board, ex))
    if not isinstance(board, dict) or not isinstance(board.get("items"), list):
        sys.exit("lanes: %s has no items list" % a.board)
    taken = board.get("fetchedAt")
    now = when(taken)
    if now is None:
        sys.exit("lanes: %s has no fetchedAt that reads as a time" % a.board)
    counts = count([i for i in board["items"] if isinstance(i, dict)], now, *config())
    print("\n".join(report(counts)))
    if a.append:
        try:
            added = append_row(a.append, taken, counts)
        except OSError as ex:
            sys.exit("lanes: cannot write %s (%s)" % (a.append, ex))
        print("%s: %s" % (os.path.basename(a.append), "added a row for %s" % taken if added else "already has a row for %s" % taken))


if __name__ == "__main__":
    main()
