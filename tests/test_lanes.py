import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tests", "fakes"))
sys.path.insert(0, HERE)
from env import FakeEnv  # noqa: E402
import lanes  # noqa: E402

LANES = os.path.join(HERE, "lanes.py")
NOW = datetime(2026, 11, 14, 12, 0, 0, tzinfo=timezone.utc)
MAINT, BOTS = ["ann"], ["robo"]
DEFAULT_BOTS = ["coderabbitai", "github-actions", "chatgpt-codex-connector", "greptile-apps", "cubic-dev-ai"]
DEFAULT_MAINT = ["morluto", "N0zoM1z0", "kaoru0822-kitauji", "baron"]


def ago(**kw):
    return (NOW - timedelta(**kw)).isoformat()


def pr(**kw):
    d = {"kind": "PR", "number": 1, "author": "dev", "createdAt": ago(days=10), "updatedAt": ago(days=1), "labels": [],
         "isDraft": False, "mergeable": "MERGEABLE", "ci": "SUCCESS", "closes": [], "namedInMain": []}
    d.update(kw)
    return d


def issue(n=50, **kw):
    d = {"kind": "issue", "number": n, "author": "dev", "createdAt": ago(days=10), "updatedAt": ago(days=1), "labels": ["bug"], "sort": "bug"}
    d.update(kw)
    return d


def lane(**kw):
    return lanes.pr_lane(pr(**kw), NOW, MAINT, BOTS)


class PrLaneTest(unittest.TestCase):
    def test_a_green_pr_is_decide_or_front_by_its_age(self):
        self.assertEqual(lane(), "decide")
        self.assertEqual(lane(createdAt=ago(days=1)), "front")

    def test_maintainers_and_bots_are_flow(self):
        self.assertEqual(lane(author="ann"), "flow")
        self.assertEqual(lane(author="robo"), "flow")
        self.assertEqual(lane(author="ANN"), "flow")
        self.assertEqual(lane(author="Robo"), "flow")
        self.assertEqual(lane(author="someone"), "decide")
        self.assertEqual(lane(author=None), "decide")

    def test_named_in_main_is_landed_only_when_the_list_is_not_empty(self):
        self.assertEqual(lane(namedInMain=["abc1234"]), "landed")
        self.assertEqual(lane(namedInMain=[]), "decide")
        self.assertEqual(lane(), "decide")
        d = pr()
        del d["namedInMain"]
        self.assertEqual(lanes.pr_lane(d, NOW, MAINT, BOTS), "decide")

    def test_first_match_wins(self):
        every = dict(isDraft=True, mergeable="CONFLICTING", ci="FAILURE", updatedAt=ago(days=90), namedInMain=["abc1234"])
        self.assertEqual(lane(author="ann", **every), "flow")
        self.assertEqual(lane(author="robo", **every), "flow")
        self.assertEqual(lane(author="dev", **every), "landed")
        stuck = dict(every, namedInMain=[])
        self.assertEqual(lane(author="dev", **stuck), "dead")
        self.assertEqual(lane(author="dev", **dict(stuck, updatedAt=ago(days=2))), "author")
        self.assertEqual(lane(author="dev", ci="PENDING", createdAt=ago(days=1)), "author")
        self.assertEqual(lane(author="dev", createdAt=ago(days=1)), "front")
        self.assertEqual(lane(author="dev", createdAt=ago(days=5)), "decide")

    def test_what_stuck_means(self):
        for label, kw in (("draft", {"isDraft": True}), ("conflicting", {"mergeable": "CONFLICTING"}),
                          ("red", {"ci": "FAILURE"}), ("error", {"ci": "ERROR"})):
            self.assertEqual(lane(updatedAt=ago(days=1), **kw), "author", label)
            self.assertEqual(lane(updatedAt=ago(days=30), **kw), "dead", label)

    def test_what_is_not_stuck(self):
        for kw in ({"mergeable": "UNKNOWN"}, {"mergeable": None}, {"mergeable": "MERGEABLE"}, {"isDraft": False}, {"isDraft": None}):
            self.assertEqual(lane(updatedAt=ago(days=30), **kw), "decide", kw)
            self.assertEqual(lane(updatedAt=ago(days=30), createdAt=ago(days=1), **kw), "front", kw)

    def test_pending_or_no_ci_is_author_however_old(self):
        for ci in ("PENDING", "EXPECTED", None, ""):
            for created in (ago(days=1), ago(days=40)):
                self.assertEqual(lane(ci=ci, createdAt=created, updatedAt=ago(days=40)), "author", (ci, created))

    def test_dead_line_is_fourteen_days_on_the_last_push(self):
        self.assertEqual(lanes.DEAD_DAYS, 14)
        self.assertEqual(lane(ci="FAILURE", pushedAt=ago(days=14)), "dead")
        self.assertEqual(lane(ci="FAILURE", pushedAt=ago(days=14, seconds=1)), "dead")
        self.assertEqual(lane(ci="FAILURE", pushedAt=ago(days=14, seconds=-1)), "author")
        self.assertEqual(lane(ci="FAILURE", pushedAt=ago(days=13, hours=23, minutes=59)), "author")
        self.assertEqual(lane(ci="FAILURE", pushedAt=ago(days=13)), "author")
        self.assertEqual(lane(ci="FAILURE", pushedAt=ago(days=200)), "dead")

    def test_front_line_is_three_days_on_the_creation_time(self):
        self.assertEqual(lanes.FRONT_DAYS, 3)
        self.assertEqual(lane(createdAt=ago(days=3)), "decide")
        self.assertEqual(lane(createdAt=ago(days=3, seconds=1)), "decide")
        self.assertEqual(lane(createdAt=ago(days=3, seconds=-1)), "front")
        self.assertEqual(lane(createdAt=ago(days=2, hours=23, minutes=59)), "front")
        self.assertEqual(lane(createdAt=ago(seconds=0)), "front")
        self.assertEqual(lane(createdAt=(NOW + timedelta(hours=1)).isoformat()), "front")

    def test_the_last_push_is_pushed_at_else_updated_at(self):
        old, new = ago(days=30), ago(days=1)
        self.assertEqual(lane(ci="FAILURE", pushedAt=old, updatedAt=new), "dead")
        self.assertEqual(lane(ci="FAILURE", pushedAt=new, updatedAt=old), "author")
        for gone in ({}, {"pushedAt": None}, {"pushedAt": ""}):
            self.assertEqual(lane(ci="FAILURE", updatedAt=old, **gone), "dead", gone)
            self.assertEqual(lane(ci="FAILURE", updatedAt=new, **gone), "author", gone)

    def test_a_missing_pushed_at_key_is_the_same_as_none(self):
        d = pr(ci="FAILURE", updatedAt=ago(days=30))
        self.assertNotIn("pushedAt", d)
        with_none = dict(d, pushedAt=None)
        self.assertEqual(lanes.pr_lane(d, NOW, MAINT, BOTS), lanes.pr_lane(with_none, NOW, MAINT, BOTS))
        self.assertEqual(lanes.pr_lane(d, NOW, MAINT, BOTS), "dead")

    def test_a_time_that_is_missing_or_unreadable_makes_no_claim(self):
        self.assertEqual(lane(ci="FAILURE", pushedAt=None, updatedAt=None), "author")
        self.assertEqual(lane(ci="FAILURE", pushedAt="not a time", updatedAt=ago(days=90)), "author")
        self.assertEqual(lane(createdAt=None), "decide")
        self.assertEqual(lane(createdAt="not a time"), "decide")
        d = pr(ci="FAILURE")
        del d["updatedAt"]
        self.assertEqual(lanes.pr_lane(d, NOW, MAINT, BOTS), "author")

    def test_times_read_with_z_microseconds_or_no_zone(self):
        self.assertEqual(lane(ci="FAILURE", pushedAt="2026-10-01T00:00:00Z"), "dead")
        self.assertEqual(lane(ci="FAILURE", pushedAt="2026-10-01T00:00:00.123456+00:00"), "dead")
        self.assertEqual(lane(ci="FAILURE", pushedAt="2026-10-01T00:00:00"), "dead")
        self.assertEqual(lane(ci="FAILURE", pushedAt="2026-11-14T00:00:00Z"), "author")
        self.assertEqual(lane(createdAt="2026-11-14T08:00:00+02:00"), "front")

    def test_maintainers_and_bots_can_be_any_collection(self):
        it = pr(author="ann")
        for coll in (["ann"], ("ann",), {"ann"}, frozenset({"ann"})):
            self.assertEqual(lanes.pr_lane(it, NOW, coll, []), "flow")
            self.assertEqual(lanes.pr_lane(it, NOW, [], coll), "flow")
        self.assertEqual(lanes.pr_lane(it, NOW, [], []), "decide")


class CountTest(unittest.TestCase):
    def count(self, items):
        return lanes.count(items, NOW, MAINT, BOTS)

    def test_an_empty_board_is_zeros_in_a_fixed_order(self):
        got = self.count([])
        self.assertEqual(list(got), ["prs", "issues"])
        self.assertEqual(list(got["prs"].items()), [(k, 0) for k in ("flow", "front", "decide", "landed", "author", "dead")])
        self.assertEqual(list(got["issues"].items()), [(k, 0) for k in ("plan", "inflight", "landed", "ask", "machine", "sample", "bug", "unsorted")])

    def test_the_order_does_not_follow_the_items(self):
        got = self.count([pr(number=1, ci="FAILURE", updatedAt=ago(days=30)), pr(number=2, author="ann"), issue(5, sort="unsorted")])
        self.assertEqual(list(got["prs"]), list(lanes.PR_LANES))
        self.assertEqual(list(got["issues"]), list(lanes.ISSUE_LANES))

    def test_every_lane_counts(self):
        items = [pr(number=1, author="ann"), pr(number=2, author="robo"),
                 pr(number=3, createdAt=ago(days=1)),
                 pr(number=4), pr(number=5), pr(number=6),
                 pr(number=7, namedInMain=["abc"]),
                 pr(number=8, isDraft=True), pr(number=9, ci="PENDING"),
                 pr(number=10, ci="FAILURE", pushedAt=ago(days=20)),
                 issue(20, sort="plan"), issue(21, sort="inflight"), issue(22, sort="landed"), issue(23, sort="ask"), issue(24, sort="ask"),
                 issue(25, sort="machine"), issue(26, sort="sample"), issue(27, sort="bug"), issue(28, sort="unsorted")]
        got = self.count(items)
        self.assertEqual(got["prs"], {"flow": 2, "front": 1, "decide": 3, "landed": 1, "author": 2, "dead": 1})
        self.assertEqual(got["issues"], {"plan": 1, "inflight": 1, "landed": 1, "ask": 2, "machine": 1, "sample": 1, "bug": 1, "unsorted": 1})
        self.assertEqual(sum(got["prs"].values()), 10)
        self.assertEqual(sum(got["issues"].values()), 9)

    def test_an_issue_counts_by_its_stored_sort_not_by_its_fields(self):
        items = [pr(number=1, author="ann", closes=[21]), issue(21, author="ann", labels=[], sort="machine"), issue(22, labels=[], sort="ask")]
        got = self.count(items)
        self.assertEqual((got["issues"]["machine"], got["issues"]["ask"], got["issues"]["plan"], got["issues"]["inflight"]), (1, 1, 0, 0))

    def test_an_issue_with_no_sort_or_an_unknown_one_counts_as_unsorted(self):
        no_sort = issue(30)
        del no_sort["sort"]
        got = self.count([no_sort, issue(31, sort=None), issue(32, sort="sorted"), issue(33, sort="")])
        self.assertEqual(got["issues"]["unsorted"], 4)
        self.assertEqual(sum(got["issues"].values()), 4)

    def test_other_kinds_are_left_out(self):
        got = self.count([{"kind": "discussion", "number": 3}, {"number": 4}, pr(), issue()])
        self.assertEqual((sum(got["prs"].values()), sum(got["issues"].values())), (1, 1))


class ConstantsTest(unittest.TestCase):
    def test_the_labels(self):
        self.assertEqual(lanes.LABELS, {
            "flow": "Maintainers' own and bots", "front": "Green, under 3 days old",
            "decide": "Green and waiting 3 days or more", "landed": "Fix already on main",
            "author": "Waiting on the author", "dead": "No push for 14 days or more", "plan": "Maintainers' plan",
            "inflight": "A pull request is open for it", "ask": "A feature, design or question",
            "machine": "Needs a Mac, Windows, a device or a paid tool", "sample": "Needs a sample file", "bug": "A bug report",
            "unsorted": "Not sorted yet"})

    def test_every_lane_has_a_label_and_only_landed_is_shared(self):
        self.assertEqual(set(lanes.LABELS), set(lanes.PR_LANES) | set(lanes.ISSUE_LANES))
        self.assertEqual(set(lanes.PR_LANES) & set(lanes.ISSUE_LANES), {"landed"})
        self.assertEqual(len(set(lanes.LABELS.values())), len(lanes.LABELS))

    def test_every_pr_lane_has_a_why(self):
        self.assertEqual(set(lanes.PR_WHY), set(lanes.PR_LANES))
        self.assertTrue(all(w and "\n" not in w for w in lanes.PR_WHY.values()))

    def test_the_columns_are_unique_with_the_kind_in_front_of_each_lane(self):
        self.assertEqual(lanes.COLUMNS[0], "taken")
        self.assertEqual(len(lanes.COLUMNS), len(set(lanes.COLUMNS)))
        self.assertEqual(lanes.COLUMNS[1:7], ["pr_" + k for k in lanes.PR_LANES])
        self.assertEqual(lanes.COLUMNS[7:], ["issue_" + k for k in lanes.ISSUE_LANES])

    def test_the_two_lines(self):
        self.assertEqual((lanes.DEAD_DAYS, lanes.FRONT_DAYS), (14, 3))


class ReportTest(unittest.TestCase):
    def test_a_total_for_each_kind_then_a_line_for_each_lane(self):
        counts = lanes.count([pr(number=1, author="ann"), pr(number=2), issue(20, sort="unsorted")], NOW, MAINT, BOTS)
        self.assertEqual(lanes.report(counts), [
            "Pull requests: 2", "  Maintainers' own and bots: 1", "  Green, under 3 days old: 0", "  Green and waiting 3 days or more: 1",
            "  Fix already on main: 0", "  Waiting on the author: 0", "  No push for 14 days or more: 0",
            "Issues: 1", "  Maintainers' plan: 0", "  A pull request is open for it: 0", "  Fix already on main: 0",
            "  A feature, design or question: 0", "  Needs a Mac, Windows, a device or a paid tool: 0", "  Needs a sample file: 0",
            "  A bug report: 0", "  Not sorted yet: 1"])


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="rea-lanes-")
        self.addCleanup(shutil.rmtree, self.d, True)

    def test_with_no_config_file_the_defaults_apply(self):
        with mock.patch.dict(os.environ, {"REA_BOARD_CONFIG": os.path.join(self.d, "none.json")}):
            self.assertEqual(lanes.config(), (DEFAULT_MAINT, DEFAULT_BOTS))

    def test_a_config_without_the_keys_gets_the_defaults(self):
        with FakeEnv({"maintainers": ["ann"]}):
            self.assertEqual(lanes.config(), (["ann"], DEFAULT_BOTS))

    def test_maintainers_and_bots_come_from_the_config(self):
        with FakeEnv({"maintainers": ["ann", "bo"], "bot_names": ["robo"]}):
            self.assertEqual(lanes.config(), (["ann", "bo"], ["robo"]))


class CliTest(unittest.TestCase):
    FETCHED = "2026-11-14T12:00:00+00:00"

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="rea-lanes-")
        self.addCleanup(shutil.rmtree, self.d, True)
        self.e = FakeEnv({"maintainers": MAINT, "bot_names": BOTS}).__enter__()
        self.addCleanup(self.e.__exit__)
        self.board = os.path.join(self.d, "board.json")
        self.stats = os.path.join(self.d, "stats.tsv")

    def put_board(self, items=None, fetched=FETCHED):
        items = [pr(number=1, author="ann"), pr(number=2), pr(number=3, createdAt=ago(days=1)), pr(number=4, ci="FAILURE", pushedAt=ago(days=20)),
                 issue(20, sort="plan"), issue(21, sort="unsorted"), issue(22)] if items is None else items
        doc = {"items": items}
        if fetched is not None:
            doc["fetchedAt"] = fetched
        with open(self.board, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)

    def run_lanes(self, *args):
        return subprocess.run([sys.executable, "-I", LANES] + list(args), capture_output=True, text=True, stdin=subprocess.DEVNULL, env=dict(os.environ))

    def tsv(self):
        with open(self.stats, encoding="utf-8") as fh:
            return [l.split("\t") for l in fh.read().splitlines()]

    HEADER = ["taken", "pr_flow", "pr_front", "pr_decide", "pr_landed", "pr_author", "pr_dead", "issue_plan", "issue_inflight", "issue_landed",
              "issue_ask", "issue_machine", "issue_sample", "issue_bug", "issue_unsorted"]
    OLD_HEADER = ["taken", "flow", "front", "decide", "landed", "author", "dead", "plan", "inflight", "sorted", "unsorted"]

    def test_it_prints_the_counts_as_plain_lines(self):
        self.put_board()
        r = self.run_lanes("--board", self.board)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), [
            "Pull requests: 4", "  Maintainers' own and bots: 1", "  Green, under 3 days old: 1", "  Green and waiting 3 days or more: 1",
            "  Fix already on main: 0", "  Waiting on the author: 0", "  No push for 14 days or more: 1",
            "Issues: 3", "  Maintainers' plan: 1", "  A pull request is open for it: 0", "  Fix already on main: 0",
            "  A feature, design or question: 0", "  Needs a Mac, Windows, a device or a paid tool: 0", "  Needs a sample file: 0",
            "  A bug report: 1", "  Not sorted yet: 1"])
        self.assertFalse(os.path.exists(self.stats))

    def test_the_counts_are_taken_at_the_boards_fetched_time(self):
        self.put_board([pr(number=1, createdAt="2026-11-12T13:00:00+00:00")], fetched="2026-11-14T12:00:00+00:00")
        self.assertIn("  Green, under 3 days old: 1", self.run_lanes("--board", self.board).stdout.splitlines())
        self.put_board([pr(number=1, createdAt="2026-11-12T13:00:00+00:00")], fetched="2026-11-15T13:00:00+00:00")
        self.assertIn("  Green and waiting 3 days or more: 1", self.run_lanes("--board", self.board).stdout.splitlines())

    def test_append_writes_a_header_and_a_row(self):
        self.put_board()
        r = self.run_lanes("--board", self.board, "--append", self.stats)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.tsv(), [self.HEADER, [self.FETCHED, "1", "1", "1", "0", "0", "1", "1", "0", "0", "0", "0", "0", "1", "1"]])
        self.assertIn("stats.tsv: added a row for " + self.FETCHED, r.stdout.splitlines())

    def test_the_same_fetched_time_adds_no_second_row(self):
        self.put_board()
        self.run_lanes("--board", self.board, "--append", self.stats)
        with open(self.stats, "rb") as fh:
            before = fh.read()
        r = self.run_lanes("--board", self.board, "--append", self.stats)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(self.stats, "rb") as fh:
            self.assertEqual(fh.read(), before)
        self.assertIn("stats.tsv: already has a row for " + self.FETCHED, r.stdout.splitlines())
        self.assertIn("Pull requests: 4", r.stdout.splitlines())

    def test_a_new_fetched_time_adds_a_row_and_the_header_stays_once(self):
        self.put_board()
        self.run_lanes("--board", self.board, "--append", self.stats)
        self.put_board([pr(number=1)], fetched="2026-11-15T12:00:00+00:00")
        self.run_lanes("--board", self.board, "--append", self.stats)
        self.put_board([], fetched="2026-11-16T12:00:00+00:00")
        self.run_lanes("--board", self.board, "--append", self.stats)
        self.run_lanes("--board", self.board, "--append", self.stats)
        rows = self.tsv()
        self.assertEqual([r[0] for r in rows], ["taken", self.FETCHED, "2026-11-15T12:00:00+00:00", "2026-11-16T12:00:00+00:00"])
        self.assertEqual(rows[0], self.HEADER)
        self.assertEqual(rows[3][1:], ["0"] * 14)
        self.assertEqual({len(r) for r in rows}, {15})

    def test_an_older_fetched_time_is_still_a_new_row(self):
        self.put_board(fetched="2026-11-15T12:00:00+00:00")
        self.run_lanes("--board", self.board, "--append", self.stats)
        self.put_board(fetched="2026-11-14T12:00:00+00:00")
        self.run_lanes("--board", self.board, "--append", self.stats)
        self.assertEqual([r[0] for r in self.tsv()[1:]], ["2026-11-15T12:00:00+00:00", "2026-11-14T12:00:00+00:00"])

    def test_an_empty_file_gets_the_header(self):
        self.put_board()
        open(self.stats, "w").close()
        self.run_lanes("--board", self.board, "--append", self.stats)
        self.assertEqual(self.tsv()[0], self.HEADER)
        self.assertEqual(len(self.tsv()), 2)

    def test_a_last_line_with_no_newline_does_not_get_the_row_glued_on(self):
        self.put_board()
        with open(self.stats, "w", encoding="utf-8") as fh:
            fh.write("\t".join(self.HEADER) + "\n" + "\t".join(["2026-11-01T00:00:00+00:00"] + ["0"] * 14))
        self.run_lanes("--board", self.board, "--append", self.stats)
        rows = self.tsv()
        self.assertEqual([r[0] for r in rows], ["taken", "2026-11-01T00:00:00+00:00", self.FETCHED])
        self.assertEqual({len(r) for r in rows}, {15})

    def test_a_row_matches_what_count_gives(self):
        self.put_board()
        with open(self.board, encoding="utf-8") as fh:
            items = json.load(fh)["items"]
        want = lanes.count(items, lanes.when(self.FETCHED), MAINT, BOTS)
        self.run_lanes("--board", self.board, "--append", self.stats)
        row = self.tsv()[1]
        self.assertEqual(row[1:], [str(want["prs"][k]) for k in lanes.PR_LANES] + [str(want["issues"][k]) for k in lanes.ISSUE_LANES])

    def test_a_stats_file_with_other_columns_stops_and_is_left_alone(self):
        self.put_board()
        old = "\t".join(self.OLD_HEADER) + "\n" + "\t".join([self.FETCHED] + ["0"] * 10) + "\n"
        for text in (old, "\t".join(self.HEADER[:-1]) + "\n", "taken\n", "\t".join(reversed(self.HEADER)) + "\n"):
            with open(self.stats, "w", encoding="utf-8") as fh:
                fh.write(text)
            r = self.run_lanes("--board", self.board, "--append", self.stats)
            self.assertNotEqual(r.returncode, 0, text)
            self.assertEqual(len(r.stderr.splitlines()), 1, r.stderr)
            self.assertIn("lanes: " + self.stats, r.stderr)
            self.assertIn("move it aside", r.stderr)
            self.assertIn("Pull requests: 4", r.stdout.splitlines())
            with open(self.stats, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), text)

    def test_a_stats_file_with_other_columns_is_refused_even_when_the_time_is_in_it(self):
        self.put_board()
        old = "\t".join(self.OLD_HEADER) + "\n" + "\t".join([self.FETCHED] + ["0"] * 10) + "\n"
        with open(self.stats, "w", encoding="utf-8") as fh:
            fh.write(old)
        r = self.run_lanes("--board", self.board, "--append", self.stats)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("already has a row", r.stdout)

    def test_without_append_the_stats_file_is_not_looked_at(self):
        self.put_board()
        with open(self.stats, "w", encoding="utf-8") as fh:
            fh.write("\t".join(self.OLD_HEADER) + "\n")
        self.assertEqual(self.run_lanes("--board", self.board).returncode, 0)

    def test_a_board_with_no_fetched_time_stops_and_writes_nothing(self):
        for fetched in (None, "", "yesterday"):
            self.put_board(fetched=fetched)
            r = self.run_lanes("--board", self.board, "--append", self.stats)
            self.assertNotEqual(r.returncode, 0, fetched)
            self.assertIn("lanes: ", r.stderr)
            self.assertFalse(os.path.exists(self.stats), fetched)

    def test_an_unreadable_board_stops_with_a_message(self):
        r = self.run_lanes("--board", os.path.join(self.d, "none.json"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("lanes: cannot read", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        with open(self.board, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        r = self.run_lanes("--board", self.board)
        self.assertIn("lanes: cannot read", r.stderr)
        with open(self.board, "w", encoding="utf-8") as fh:
            fh.write("[]")
        r = self.run_lanes("--board", self.board)
        self.assertIn("lanes: ", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_a_stats_file_in_a_missing_folder_stops_with_a_message(self):
        self.put_board()
        r = self.run_lanes("--board", self.board, "--append", os.path.join(self.d, "gone", "stats.tsv"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("lanes: cannot write", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_it_runs_with_no_config_file(self):
        self.put_board([pr(number=1, author="coderabbitai"), pr(number=2), issue(20, sort="unsorted")])
        env = dict(os.environ, REA_BOARD_CONFIG=os.path.join(self.d, "none.json"))
        r = subprocess.run([sys.executable, "-I", LANES, "--board", self.board, "--append", self.stats], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("  Maintainers' own and bots: 1", r.stdout.splitlines())
        self.assertIn("  Not sorted yet: 1", r.stdout.splitlines())
        self.assertEqual(len(self.tsv()), 2)

    def test_items_that_are_not_objects_are_passed_over(self):
        self.put_board([pr(number=1), "x", None, issue(20)])
        r = self.run_lanes("--board", self.board)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Pull requests: 1", r.stdout.splitlines())
        self.assertIn("Issues: 1", r.stdout.splitlines())


if __name__ == "__main__":
    unittest.main()
