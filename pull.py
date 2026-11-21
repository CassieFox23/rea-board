#!/usr/bin/env python3
"""Pull every open pull request and issue of morluto/rea into board.json, sort them, add the counts to stats.tsv.

usage: pull.py

Reads public GitHub data through gh and posts nothing. Files go in the data folder (config data_dir, default data/ in
this repo): board.json, the board before it as board.prev.json, board.html (the page page.py draws from the board) and
stats.tsv. Each item gets a sort and a why: a PR's from lanes.py, an issue's from sort.py, which reads the title and
labels. A local bare clone of the repo (config mirror) is optional: with it, a pull request or issue that a main commit
message names as #N gets that commit in namedInMain; without it namedInMain is empty.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conf  # noqa: E402
import lanes  # noqa: E402
import page  # noqa: E402
import sort  # noqa: E402

REPO = conf.repo()
REPO_OWNER, REPO_NAME = REPO.split("/", 1)
RETRY_WAITS = (2, 5, 10, 20)
FINAL = re.compile(r"HTTP 40[14]|Bad credentials|gh auth login|Could not resolve to a")
MERGE_WAITS = (5, 10, 20)
MERGE_BATCH = 50

PR_QUERY = """query($cursor: String) {
  rateLimit { cost remaining }
  repository(owner: "%s", name: "%s") {
    pullRequests(states: OPEN, first: 50, after: $cursor, orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title url createdAt updatedAt isDraft additions deletions changedFiles mergeable
        authorAssociation
        author { login }
        labels(first: 20) { totalCount nodes { name } }
        commits(last: 1) { nodes { commit { committedDate statusCheckRollup { state } } } }
        closingIssuesReferences(first: 10) { totalCount nodes { number } }
      }
    }
  }
}""" % (REPO_OWNER, REPO_NAME)

ISSUE_QUERY = """query($cursor: String) {
  rateLimit { cost remaining }
  repository(owner: "%s", name: "%s") {
    issues(states: OPEN, first: 50, after: $cursor, orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title url createdAt updatedAt authorAssociation
        author { login }
        labels(first: 20) { totalCount nodes { name } }
      }
    }
  }
}""" % (REPO_OWNER, REPO_NAME)

COST = {"total": 0, "remaining": None, "calls": 0}


def gql(query, **variables):
    if not query.lstrip().startswith("query"):
        sys.exit("gql: refusing to send anything but a query")
    cmd = ["gh", "api", "graphql", "-f", "query=" + query]
    for k, v in variables.items():
        if v is not None:
            cmd += ["-f", "%s=%s" % (k, v)]
    r = None
    for attempt in range(len(RETRY_WAITS) + 1):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True)
        except FileNotFoundError:
            sys.exit("gh not found: install the GitHub CLI and log in with gh auth login")
        if r.returncode == 0:
            break
        sys.stderr.write(r.stderr)
        if FINAL.search(r.stderr):
            sys.exit("gh failed with exit code %d; a retry will not help" % r.returncode)
        if attempt < len(RETRY_WAITS):
            sys.stderr.write("retry %d of %d in %ds\n" % (attempt + 1, len(RETRY_WAITS), RETRY_WAITS[attempt]))
            time.sleep(RETRY_WAITS[attempt])
    if r.returncode != 0:
        sys.exit("gh failed with exit code %d after %d retries" % (r.returncode, len(RETRY_WAITS)))
    data = json.loads(r.stdout)
    if "errors" in data:
        sys.exit("graphql errors: %s" % json.dumps(data["errors"]))
    rl = data["data"]["rateLimit"]
    COST["total"] += rl["cost"]
    COST["remaining"] = rl["remaining"]
    COST["calls"] += 1
    return data["data"]


def paged(query, getter, **variables):
    out = []
    cursor = None
    while True:
        d = gql(query, cursor=cursor, **variables)
        conn = getter(d)
        out += conn["nodes"]
        if not conn["pageInfo"]["hasNextPage"]:
            return out
        cursor = conn["pageInfo"]["endCursor"]


def read_all(n, field):
    """The nodes of a connection on item n, with a warning when GitHub has more than the query asked for."""
    conn = n[field]
    if conn.get("totalCount", 0) > len(conn["nodes"]):
        sys.stderr.write("#%d: %s has %d, only the first %d were read\n" % (n["number"], field, conn["totalCount"], len(conn["nodes"])))
    return conn["nodes"]


def norm_pr(n):
    commits = n["commits"]["nodes"]
    roll = None
    if commits and commits[0]["commit"]["statusCheckRollup"]:
        roll = commits[0]["commit"]["statusCheckRollup"]["state"]
    pushed = commits[0]["commit"].get("committedDate") if commits else None
    return {
        "kind": "PR",
        "number": n["number"],
        "title": n["title"],
        "author": (n["author"] or {}).get("login", "ghost"),
        "association": n["authorAssociation"],
        "createdAt": n["createdAt"],
        "updatedAt": n["updatedAt"],
        "labels": sorted(l["name"] for l in read_all(n, "labels")),
        "url": n["url"],
        "isDraft": n["isDraft"],
        "additions": n["additions"],
        "deletions": n["deletions"],
        "changedFiles": n["changedFiles"],
        "mergeable": n["mergeable"],
        "ci": roll,
        "pushedAt": pushed,
        "closes": sorted(c["number"] for c in read_all(n, "closingIssuesReferences")),
    }


def merge_query(numbers):
    pulls = "\n".join("    p%d: pullRequest(number: %d) { number mergeable }" % (n, n) for n in numbers)
    return """query {
  rateLimit { cost remaining }
  repository(owner: "%s", name: "%s") {
%s
  }
}""" % (REPO_OWNER, REPO_NAME, pulls)


def settle_mergeable(prs):
    unknown = [p for p in prs if p["mergeable"] == "UNKNOWN"]
    for wait in MERGE_WAITS:
        if not unknown:
            break
        time.sleep(wait)
        by_number = {p["number"]: p for p in unknown}
        for i in range(0, len(unknown), MERGE_BATCH):
            d = gql(merge_query([p["number"] for p in unknown[i:i + MERGE_BATCH]]))
            for n in d["repository"].values():
                if n and n["mergeable"] != "UNKNOWN":
                    by_number[n["number"]]["mergeable"] = n["mergeable"]
        unknown = [p for p in unknown if p["mergeable"] == "UNKNOWN"]
    return len(unknown)


def norm_issue(n):
    return {
        "kind": "issue",
        "number": n["number"],
        "title": n["title"],
        "author": (n["author"] or {}).get("login", "ghost"),
        "association": n["authorAssociation"],
        "createdAt": n["createdAt"],
        "updatedAt": n["updatedAt"],
        "labels": sorted(l["name"] for l in read_all(n, "labels")),
        "url": n["url"],
    }


def named_in_main():
    mirror = conf.mirror()
    if not mirror:
        return {}
    r = subprocess.run(["git", "-C", mirror, "fetch", "-q", "origin", "+refs/heads/main:refs/heads/main"], capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        sys.exit("mirror fetch failed with exit code %d" % r.returncode)
    r = subprocess.run(["git", "-C", mirror, "log", "refs/heads/main", "--since=" + conf.main_since(),
                        "--format=%H%x1f%B%x1e"], capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        sys.exit("mirror log failed with exit code %d" % r.returncode)
    hits = {}
    for rec in r.stdout.split("\x1e"):
        rec = rec.strip("\n")
        if not rec:
            continue
        sha, _, msg = rec.partition("\x1f")
        for n in set(re.findall(r"(?<![\w/])#(\d+)\b", msg)):
            hits.setdefault(int(n), []).append(sha)
    return hits


def sort_items(prs, issues, now):
    """Give each PR and issue its sort and why."""
    maintainers, bots = lanes.config()
    for p in prs:
        p["sort"] = lanes.pr_lane(p, now, maintainers, bots)
        p["why"] = lanes.PR_WHY[p["sort"]]
    closed_by = {}
    for p in prs:
        for n in p["closes"]:
            closed_by.setdefault(n, []).append(p["number"])
    plan_authors, unsorted_labels = sort.config()
    for it in issues:
        it["sort"], it["why"] = sort.issue_sort(it, closed_by, plan_authors, unsorted_labels)


def replace_atomic(path, write):
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=".board-", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            write(fh)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_board(board_path, prev_path, data):
    d = os.path.dirname(os.path.abspath(board_path))
    fd, tmp = tempfile.mkstemp(prefix=".board-", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
        if os.path.exists(board_path):
            with open(board_path, encoding="utf-8") as f:
                old = f.read()
            replace_atomic(prev_path, lambda fh: fh.write(old))
        os.replace(tmp, board_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main():
    ap = argparse.ArgumentParser(
        description="Pull every open %s PR and issue into board.json, sort them and add the counts to stats.tsv." % REPO,
        epilog="Files go in the data folder (config data_dir, default data/ in this repo): board.json, board.prev.json, board.html, stats.tsv. "
               "A local bare clone of the repo (config mirror) is optional; without one, namedInMain is empty.")
    ap.parse_args()
    t0 = time.time()
    data = conf.data_dir()
    os.makedirs(data, exist_ok=True)
    board_json = os.path.join(data, "board.json")
    board_html = os.path.join(data, "board.html")
    stats_tsv = os.path.join(data, "stats.tsv")
    prs = [norm_pr(n) for n in paged(PR_QUERY, lambda d: d["repository"]["pullRequests"])]
    still_unknown = settle_mergeable(prs)
    iss = [norm_issue(n) for n in paged(ISSUE_QUERY, lambda d: d["repository"]["issues"])]
    items = prs + iss
    hits = named_in_main()
    for it in items:
        it["namedInMain"] = hits.get(it["number"], [])

    prev_keys = None
    if os.path.exists(board_json):
        try:
            with open(board_json, encoding="utf-8") as f:
                prev_keys = {(i["kind"], i["number"]) for i in json.load(f)["items"]}
        except (OSError, ValueError, KeyError, TypeError) as err:
            sys.stderr.write("the old board.json could not be read (%s), so this pull counts as the first\n" % err)
    first_run = prev_keys is None
    for it in items:
        it["new"] = (not first_run) and (it["kind"], it["number"]) not in prev_keys

    now = datetime.now(timezone.utc)
    taken = now.isoformat()
    sort_items(prs, iss, now)
    save_board(board_json, os.path.join(data, "board.prev.json"), {
        "fetchedAt": taken, "firstRun": first_run, "graphqlCost": COST["total"], "graphqlRemaining": COST["remaining"],
        "items": items})
    try:
        page_size = page.write(items, now, board_html)
    except OSError as ex:
        sys.exit("pull: cannot write %s (%s)" % (board_html, ex))
    named = "%d named in main" % sum(1 for i in items if i["namedInMain"]) if conf.mirror() else "named in main: no mirror set"
    print("%d PRs, %d issues, %d new%s, %s, %d merge states unknown, %.1fs, graphql cost %d (%d calls, %s left)" % (
        len(prs), len(iss), sum(1 for i in items if i["new"]), " (first run)" if first_run else "", named,
        still_unknown, time.time() - t0, COST["total"], COST["calls"], COST["remaining"]))
    counts = lanes.count(items, now, *lanes.config())
    print("\n".join(lanes.report(counts)))
    print("%s: written, %.1f KB" % (os.path.basename(board_html), page_size / 1024))
    try:
        added = lanes.append_row(stats_tsv, taken, counts)
    except OSError as ex:
        sys.exit("pull: cannot write %s (%s)" % (stats_tsv, ex))
    print("%s: %s" % (os.path.basename(stats_tsv), "added a row for %s" % taken if added else "already has a row for %s" % taken))


if __name__ == "__main__":
    main()
