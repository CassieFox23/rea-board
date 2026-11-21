import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tests", "fakes"))
sys.path.insert(0, HERE)
from env import FakeEnv  # noqa: E402

with FakeEnv():
    import pull  # noqa: E402
import lanes  # noqa: E402
import page as board_page  # noqa: E402

PULL = os.path.join(HERE, "pull.py")
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t", "-c", "commit.gpgsign=false"]
GIT_ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
STAMP = datetime(2026, 11, 14, 12, 0, 0, tzinfo=timezone.utc)


def pr_node(commits=(), number=7, mergeable="MERGEABLE", author="a", created="2026-01-01T00:00:00Z", closes=(3,)):
    return {"number": number, "title": "t%d" % number, "url": "u", "createdAt": created, "updatedAt": "2026-01-02T00:00:00Z",
            "isDraft": False, "additions": 1, "deletions": 1, "changedFiles": 1, "mergeable": mergeable,
            "authorAssociation": "NONE", "author": {"login": author} if author else None, "labels": {"nodes": []},
            "commits": {"nodes": list(commits)}, "closingIssuesReferences": {"nodes": [{"number": c} for c in closes]}}


def issue_node(number=20, author="a", labels=(), title=None):
    return {"number": number, "title": title or "i%d" % number, "url": "u", "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-02T00:00:00Z",
            "authorAssociation": "NONE", "author": {"login": author} if author else None, "labels": {"nodes": [{"name": l} for l in labels]}}


def page(nodes):
    return {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": nodes}


def git(cwd, *args, **env):
    r = subprocess.run(GIT + list(args), cwd=cwd, capture_output=True, text=True, env=dict(GIT_ENV, **env))
    if r.returncode != 0:
        raise AssertionError("git %s failed: %s" % (" ".join(args), r.stderr))
    return r.stdout.strip()


class SaveBoardTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="rea-save-")
        self.addCleanup(shutil.rmtree, self.d, True)
        self.board_path = os.path.join(self.d, "board.json")
        self.prev_path = os.path.join(self.d, "board.prev.json")

    def _read_json(self, path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def test_first_save_no_prev(self):
        """A first save with no existing board_path writes board_path and no prev_path."""
        pull.save_board(self.board_path, self.prev_path, {"fetchedAt": "2026-01-01T00:00:00Z", "items": []})
        self.assertTrue(os.path.exists(self.board_path))
        self.assertFalse(os.path.exists(self.prev_path))
        self.assertEqual(self._read_json(self.board_path)["fetchedAt"], "2026-01-01T00:00:00Z")

    def test_second_save_leaves_prev(self):
        """A second save leaves prev_path holding the first board and board_path the second."""
        pull.save_board(self.board_path, self.prev_path, {"fetchedAt": "2026-01-01T00:00:00Z", "items": [{"kind": "PR", "number": 1}]})
        pull.save_board(self.board_path, self.prev_path, {"fetchedAt": "2026-02-01T00:00:00Z", "items": [{"kind": "PR", "number": 2}]})
        self.assertEqual(self._read_json(self.board_path)["fetchedAt"], "2026-02-01T00:00:00Z")
        self.assertEqual(self._read_json(self.prev_path)["fetchedAt"], "2026-01-01T00:00:00Z")
        self.assertEqual(self._read_json(self.prev_path)["items"][0]["number"], 1)

    def test_dump_error_restores_old_and_cleans_temp(self):
        """When json.dump raises partway through, board_path still holds the old board byte for byte and no temp file is left."""
        pull.save_board(self.board_path, self.prev_path, {"fetchedAt": "2026-01-01T00:00:00Z", "items": []})
        with open(self.board_path, encoding="utf-8") as fh:
            old_bytes = fh.read()
        original_dump = json.dump
        raised = False

        def bad_dump(obj, fp, *a, **kw):
            nonlocal raised
            if not raised:
                raised = True
                raise ValueError("cut-off!")
            return original_dump(obj, fp, *a, **kw)

        with mock.patch.object(json, "dump", bad_dump):
            with self.assertRaises(ValueError):
                pull.save_board(self.board_path, self.prev_path, {"fetchedAt": "2026-06-01T00:00:00Z", "items": [1, 2]})
        with open(self.board_path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), old_bytes)
        self.assertEqual(os.listdir(self.d), ["board.json"])


class NormPrTest(unittest.TestCase):
    def test_the_last_commits_date_is_pushed_at_and_its_rollup_is_ci(self):
        """A PR with a last commit gets that commit's committedDate as pushedAt, next to ci."""
        got = pull.norm_pr(pr_node([{"commit": {"committedDate": "2026-01-02T03:04:05Z", "statusCheckRollup": {"state": "SUCCESS"}}}]))
        self.assertEqual((got["pushedAt"], got["ci"]), ("2026-01-02T03:04:05Z", "SUCCESS"))
        self.assertEqual((got["number"], got["updatedAt"], got["closes"]), (7, "2026-01-02T00:00:00Z", [3]))

    def test_a_commit_with_no_rollup_still_has_its_date(self):
        """A last commit with no status rollup gives its date as pushedAt and None as ci."""
        got = pull.norm_pr(pr_node([{"commit": {"committedDate": "2026-01-02T03:04:05Z", "statusCheckRollup": None}}]))
        self.assertEqual((got["pushedAt"], got["ci"]), ("2026-01-02T03:04:05Z", None))

    def test_a_pr_with_no_commit_has_none_for_both(self):
        """A PR whose commit list is empty has pushedAt None, the key still there, and ci None."""
        got = pull.norm_pr(pr_node([]))
        self.assertIn("pushedAt", got)
        self.assertEqual((got["pushedAt"], got["ci"]), (None, None))

    def test_a_commit_node_with_no_date_gives_none(self):
        """A commit node with no committedDate gives None, not a KeyError."""
        got = pull.norm_pr(pr_node([{"commit": {"statusCheckRollup": None}}]))
        self.assertIsNone(got["pushedAt"])

    def test_the_query_asks_for_the_date_in_the_same_commit_selection(self):
        """PR_QUERY gets committedDate inside its one commits(last: 1) selection, with no second query."""
        self.assertEqual(pull.PR_QUERY.count("committedDate"), 1)
        self.assertEqual(pull.PR_QUERY.count("commits("), 1)
        self.assertRegex(pull.PR_QUERY, r"commits\(last: 1\) \{ nodes \{ commit \{ committedDate statusCheckRollup \{ state \} \} \} \}")

    def test_the_item_keys(self):
        """A PR item has exactly these keys, and closes and labels are sorted."""
        node = pr_node(closes=(9, 3))
        node["labels"] = {"nodes": [{"name": "b"}, {"name": "a"}]}
        got = pull.norm_pr(node)
        self.assertEqual(sorted(got), sorted([
            "kind", "number", "title", "author", "association", "createdAt", "updatedAt", "labels", "url", "isDraft", "additions",
            "deletions", "changedFiles", "mergeable", "ci", "pushedAt", "closes"]))
        self.assertEqual((got["kind"], got["labels"], got["closes"]), ("PR", ["a", "b"], [3, 9]))

    def test_a_deleted_author_is_ghost(self):
        self.assertEqual(pull.norm_pr(pr_node(author=None))["author"], "ghost")


class NormIssueTest(unittest.TestCase):
    def test_the_item_keys(self):
        """An issue item has exactly these keys, with the labels sorted."""
        got = pull.norm_issue(issue_node(labels=("b", "a")))
        self.assertEqual(sorted(got), sorted(["kind", "number", "title", "author", "association", "createdAt", "updatedAt", "labels", "url"]))
        self.assertEqual((got["kind"], got["number"], got["labels"]), ("issue", 20, ["a", "b"]))

    def test_a_deleted_author_is_ghost(self):
        self.assertEqual(pull.norm_issue(issue_node(author=None))["author"], "ghost")

    def test_the_query_has_no_pr_fields(self):
        self.assertIn("issues(states: OPEN", pull.ISSUE_QUERY)
        self.assertNotIn("commits(", pull.ISSUE_QUERY)

    def test_neither_query_asks_for_a_body(self):
        self.assertNotIn("body", pull.ISSUE_QUERY)
        self.assertNotIn("body", pull.PR_QUERY)

    def test_both_lists_page_by_a_key_that_does_not_move(self):
        """Both lists page by createdAt, oldest first."""
        for q in (pull.PR_QUERY, pull.ISSUE_QUERY):
            self.assertIn("orderBy: {field: CREATED_AT, direction: ASC}", q)
            self.assertNotIn("UPDATED_AT", q)


class SortItemsTest(unittest.TestCase):
    NOW = STAMP

    def sorted_items(self, prs, issues, **config):
        with FakeEnv(dict({"maintainers": ["ann"], "bot_names": ["robo"], "plan_authors": ["cy"]}, **config)):
            pull.sort_items(prs, issues, self.NOW)
        return {i["number"]: (i["sort"], i["why"]) for i in prs + issues}

    def pr(self, number, **kw):
        return dict({"kind": "PR", "number": number, "author": "a", "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-02T00:00:00Z",
                     "isDraft": False, "mergeable": "MERGEABLE", "ci": "SUCCESS", "closes": [], "namedInMain": []}, **kw)

    def issue(self, number, **kw):
        return dict({"kind": "issue", "number": number, "title": "i%d" % number, "author": "a", "labels": [], "namedInMain": []}, **kw)

    def test_a_pr_gets_its_lane_and_a_why(self):
        got = self.sorted_items([self.pr(1, author="ann"), self.pr(2), self.pr(3, namedInMain=["abc"])], [])
        self.assertEqual([got[n][0] for n in (1, 2, 3)], ["flow", "decide", "landed"])
        self.assertEqual([got[n][1] for n in (1, 2, 3)], [lanes.PR_WHY[k] for k in ("flow", "decide", "landed")])

    def test_an_issue_closed_by_an_open_pr_is_inflight_and_the_why_names_the_pr(self):
        got = self.sorted_items([self.pr(8, closes=[21]), self.pr(5, closes=[21, 22])], [self.issue(21), self.issue(22), self.issue(23)])
        self.assertEqual(got[21], ("inflight", "open PR #5 closes it"))
        self.assertEqual(got[22], ("inflight", "open PR #5 closes it"))
        self.assertEqual(got[23][0], "unsorted")

    def test_an_issue_named_in_main_is_landed(self):
        got = self.sorted_items([], [self.issue(21, namedInMain=["abcdef1234"]), self.issue(22)])
        self.assertEqual(got[21], ("landed", "commit abcdef1 on main mentions it"))
        self.assertEqual(got[22][0], "unsorted")

    def test_the_title_is_read_for_the_sort(self):
        got = self.sorted_items([], [self.issue(21, title="Only seen on macOS"), self.issue(22)])
        self.assertEqual(got[21], ("machine", "title mentions macOS"))
        self.assertEqual(got[22][0], "unsorted")

    def test_the_plan_set_and_the_unsorted_labels_come_from_the_config(self):
        issues = [self.issue(21, author="cy"), self.issue(22, author="ann"), self.issue(23, labels=["enhancement"])]
        self.assertEqual([self.sorted_items([], issues)[n][0] for n in (21, 22, 23)], ["plan", "plan", "ask"])
        issues = [self.issue(21, author="cy"), self.issue(23, labels=["enhancement"])]
        got = self.sorted_items([], issues, plan_authors=[], maintainers=[], unsorted_labels=["enhancement"])
        self.assertEqual([got[n][0] for n in (21, 23)], ["unsorted", "unsorted"])


class SettleMergeableTest(unittest.TestCase):
    def setUp(self):
        self.script = {}
        self.gql = mock.patch.object(pull, "gql", side_effect=self._gql).start()
        self.sleep = mock.patch.object(pull.time, "sleep").start()
        self.addCleanup(mock.patch.stopall)

    def _gql(self, query, **variables):
        out = {}
        for n in map(int, re.findall(r"pullRequest\(number: (\d+)\)", query)):
            seq = self.script.get(n, [])
            self.script[n] = seq[1:]
            out["p%d" % n] = {"number": n, "mergeable": seq[0] if seq else "UNKNOWN"}
        return {"repository": out}

    def _asked(self):
        return [[int(n) for n in re.findall(r"pullRequest\(number: (\d+)\)", c.args[0])] for c in self.gql.call_args_list]

    def _prs(self, *states):
        return [{"kind": "PR", "number": i + 1, "mergeable": m} for i, m in enumerate(states)]

    def test_unknown_are_asked_again_and_updated(self):
        """PRs that come back UNKNOWN are asked again by number; each answer that is no longer UNKNOWN replaces it, and the rest are asked once more."""
        prs = self._prs("UNKNOWN", "UNKNOWN", "MERGEABLE", "CONFLICTING")
        self.script = {1: ["MERGEABLE"], 2: ["UNKNOWN", "CONFLICTING"]}
        left = pull.settle_mergeable(prs)
        self.assertEqual([p["mergeable"] for p in prs], ["MERGEABLE", "CONFLICTING", "MERGEABLE", "CONFLICTING"])
        self.assertEqual(left, 0)
        self.assertEqual(self._asked(), [[1, 2], [2]])
        self.assertEqual([c.args for c in self.sleep.call_args_list], [(5,), (10,)])
        for c in self.gql.call_args_list:
            q = c.args[0]
            self.assertTrue(q.lstrip().startswith("query"))
            self.assertIn("rateLimit { cost remaining }", q)
            self.assertIn('repository(owner: "morluto", name: "rea")', q)
        self.assertIn("p1: pullRequest(number: 1) { number mergeable }", self.gql.call_args_list[0].args[0])

    def test_still_unknown_after_the_cap_stay_unknown_and_are_counted(self):
        """PRs still UNKNOWN after every round stay UNKNOWN, are counted, and the rounds stop at the cap."""
        prs = self._prs("UNKNOWN", "UNKNOWN", "UNKNOWN")
        self.script = {1: ["CONFLICTING"]}
        left = pull.settle_mergeable(prs)
        self.assertEqual([p["mergeable"] for p in prs], ["CONFLICTING", "UNKNOWN", "UNKNOWN"])
        self.assertEqual(left, 2)
        self.assertEqual(self._asked(), [[1, 2, 3], [2, 3], [2, 3]])
        self.assertEqual([c.args for c in self.sleep.call_args_list], [(5,), (10,), (20,)])

    def test_no_unknown_makes_no_call(self):
        """With no UNKNOWN PR there is no gql call and no wait."""
        prs = self._prs("MERGEABLE", "CONFLICTING")
        left = pull.settle_mergeable(prs)
        self.assertEqual(left, 0)
        self.gql.assert_not_called()
        self.sleep.assert_not_called()
        self.assertEqual([p["mergeable"] for p in prs], ["MERGEABLE", "CONFLICTING"])

    def test_batches_are_the_constants_size(self):
        """120 unknown PRs go out in three calls of MERGE_BATCH (50), 50 and 20, and every one is updated."""
        prs = self._prs(*["UNKNOWN"] * 120)
        self.script = {n: ["MERGEABLE"] for n in range(1, 121)}
        left = pull.settle_mergeable(prs)
        self.assertEqual(pull.MERGE_BATCH, 50)
        self.assertEqual([len(a) for a in self._asked()], [50, 50, 20])
        self.assertEqual(sorted(n for a in self._asked() for n in a), list(range(1, 121)))
        self.assertEqual(left, 0)
        self.assertTrue(all(p["mergeable"] == "MERGEABLE" for p in prs))


class GqlTest(unittest.TestCase):
    def setUp(self):
        self.e = FakeEnv().__enter__()
        self.addCleanup(self.e.__exit__)
        self.sleep = mock.patch.object(pull.time, "sleep").start()
        self.addCleanup(mock.patch.stopall)
        cost = mock.patch.dict(pull.COST, {"total": 0, "remaining": None, "calls": 0})
        cost.start()
        self.addCleanup(cost.stop)

    def test_it_returns_the_data_and_adds_the_cost(self):
        self.e.gh_fixture("q", match=r"^api graphql ", json={"data": {"rateLimit": {"cost": 2, "remaining": 4990}, "x": 1}})
        d = pull.gql("query { x }")
        self.assertEqual(d["x"], 1)
        self.assertEqual(pull.COST, {"total": 2, "remaining": 4990, "calls": 1})
        self.assertEqual([c[:3] for c in self.e.gh_calls()], [["api", "graphql", "-f"]])

    def test_a_gh_failure_is_retried_then_stops(self):
        self.e.gh_fixture("q", match=r"^api graphql ", stderr="boom\n", exit=1)
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                pull.gql("query { x }")
        self.assertIn("gh failed with exit code 1 after 4 retries", str(cm.exception))
        self.assertEqual(len(self.e.gh_calls()), 5)
        self.assertEqual([c.args for c in self.sleep.call_args_list], [(2,), (5,), (10,), (20,)])

    def test_an_error_a_retry_cannot_fix_stops_at_once(self):
        self.e.gh_fixture("q", match=r"^api graphql ", stderr="HTTP 401: Bad credentials\n", exit=1)
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                pull.gql("query { x }")
        self.assertIn("a retry will not help", str(cm.exception))
        self.assertEqual(len(self.e.gh_calls()), 1)
        self.sleep.assert_not_called()

    def test_a_missing_gh_stops_with_a_message(self):
        with mock.patch.object(pull.subprocess, "run", side_effect=FileNotFoundError("gh")):
            with self.assertRaises(SystemExit) as cm:
                pull.gql("query { x }")
        self.assertIn("gh not found", str(cm.exception))

    def test_anything_but_a_query_is_refused_before_gh_runs(self):
        with self.assertRaises(SystemExit) as cm:
            pull.gql("mutation { x }")
        self.assertIn("refusing", str(cm.exception))
        self.assertEqual(self.e.gh_calls(), [])

    def test_graphql_errors_stop_it(self):
        self.e.gh_fixture("q", match=r"^api graphql ", json={"errors": [{"message": "no"}]})
        with self.assertRaises(SystemExit) as cm:
            pull.gql("query { x }")
        self.assertIn("graphql errors", str(cm.exception))


class NamedInMainTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="rea-mirror-")
        self.addCleanup(shutil.rmtree, self.d, True)
        self.e = FakeEnv().__enter__()
        self.addCleanup(self.e.__exit__)

    def mirror_config(self, mirror, **more):
        self.e.write_config(dict({"mirror": mirror}, **more))

    def make_mirror(self, *messages, date=None):
        self.origin = os.path.join(self.d, "origin")
        os.mkdir(self.origin)
        git(self.origin, "init", "-q", "-b", "main")
        shas = [self.commit(m, date) for m in messages]
        self.mirror = os.path.join(self.d, "mirror.git")
        git(self.d, "clone", "-q", "--mirror", self.origin, self.mirror)
        return shas

    def commit(self, message, date=None):
        when = {"GIT_COMMITTER_DATE": date, "GIT_AUTHOR_DATE": date} if date else {}
        git(self.origin, "commit", "-q", "--allow-empty", "-m", message, **when)
        return git(self.origin, "rev-parse", "HEAD")

    def test_with_no_mirror_it_is_empty_and_runs_no_command(self):
        with mock.patch.object(pull.subprocess, "run") as run:
            self.assertEqual(pull.named_in_main(), {})
        run.assert_not_called()

    def test_it_fetches_and_maps_each_number_to_the_commits_that_name_it(self):
        first, second = self.make_mirror("Fix the thing (#12), see owner/repo#99 and #12 again", "Merge #13 and #14\n\nCloses: #12")
        self.mirror_config(self.mirror)
        got = pull.named_in_main()
        self.assertEqual(sorted(got), [12, 13, 14])
        self.assertEqual(sorted(got[12]), sorted([first, second]))
        self.assertEqual((got[13], got[14]), ([second], [second]))

    def test_a_number_inside_a_word_or_after_a_slash_is_not_a_mention(self):
        self.make_mirror("C#5 and repo#6 and owner/repo#7 and #8")
        self.mirror_config(self.mirror)
        self.assertEqual(sorted(pull.named_in_main()), [8])

    def test_it_fetches_before_it_reads(self):
        self.make_mirror("first (#1)")
        self.mirror_config(self.mirror)
        self.assertEqual(sorted(pull.named_in_main()), [1])
        later = self.commit("later (#15)")
        self.assertEqual(pull.named_in_main()[15], [later])

    def test_a_plain_bare_clone_is_brought_up_to_date_too(self):
        self.make_mirror("first (#1)")
        bare = os.path.join(self.d, "bare.git")
        git(self.d, "clone", "-q", "--bare", self.origin, bare)
        self.mirror_config(bare)
        later = self.commit("later (#16)")
        self.assertEqual(pull.named_in_main()[16], [later])

    def test_main_since_limits_the_log(self):
        self.make_mirror("dated (#1)", date="2020-06-15T12:00:00+00:00")
        self.mirror_config(self.mirror, main_since="2021-01-01")
        self.assertEqual(pull.named_in_main(), {})
        self.mirror_config(self.mirror, main_since="2020-01-01")
        self.assertEqual(sorted(pull.named_in_main()), [1])

    def test_a_mirror_that_cannot_be_fetched_stops_with_a_message(self):
        self.mirror_config(os.path.join(self.d, "none.git"))
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                pull.named_in_main()
        self.assertIn("mirror fetch failed", str(cm.exception))


class MainTest(unittest.TestCase):
    def setUp(self):
        self.e = FakeEnv().__enter__()
        self.addCleanup(self.e.__exit__)
        d = tempfile.mkdtemp(prefix="rea-main-")
        self.addCleanup(shutil.rmtree, d, True)
        self.data = os.path.join(d, "data")
        self.e.write_config({"data_dir": self.data, "maintainers": ["ann"], "bot_names": ["robo"], "plan_authors": ["cy"]})
        self.prs = [pr_node(number=1, mergeable="UNKNOWN", author="ann"), pr_node(number=2, mergeable="UNKNOWN"), pr_node(number=3, mergeable="CONFLICTING")]
        self.issues = [issue_node(20, author="cy"), issue_node(21), issue_node(22, labels=("bug",))]
        self.script = {1: ["MERGEABLE"]}
        self.gql = mock.patch.object(pull, "gql", side_effect=self._gql).start()
        mock.patch.object(pull.time, "sleep").start()
        cost = mock.patch.dict(pull.COST, {"total": 0, "remaining": None, "calls": 0})
        cost.start()
        self.addCleanup(mock.patch.stopall)
        self.addCleanup(cost.stop)

    def _gql(self, query, **variables):
        if "pullRequests(" in query:
            return {"repository": {"pullRequests": page(self.prs)}}
        if "issues(" in query:
            return {"repository": {"issues": page(self.issues)}}
        out = {}
        for n in map(int, re.findall(r"pullRequest\(number: (\d+)\)", query)):
            seq = self.script.get(n, [])
            self.script[n] = seq[1:]
            out["p%d" % n] = {"number": n, "mergeable": seq[0] if seq else "UNKNOWN"}
        return {"repository": out}

    def run_main(self, now=None):
        out = io.StringIO()
        patches = [mock.patch.object(sys, "argv", ["pull.py"])]
        if now is not None:
            class Fixed(datetime):
                @classmethod
                def now(cls, tz=None):
                    return now

            patches.append(mock.patch.object(pull, "datetime", Fixed))
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            stack.enter_context(contextlib.redirect_stdout(out))
            pull.main()
        return out.getvalue()

    def read(self, name):
        with open(os.path.join(self.data, name), encoding="utf-8") as fh:
            return fh.read()

    def board(self, name="board.json"):
        return json.loads(self.read(name))

    def stats(self):
        return [l.split("\t") for l in self.read("stats.tsv").splitlines()]

    def test_it_saves_the_board_and_the_summary_says_how_many_merge_states_are_unknown(self):
        out = self.run_main()
        first = out.splitlines()[0]
        self.assertTrue(first.startswith("3 PRs, 3 issues, 0 new (first run), named in main: no mirror set, 1 merge states unknown, "), first)
        self.assertIn("graphql cost 0 (0 calls, None left)", first)
        b = self.board()
        self.assertEqual(sorted(b), ["fetchedAt", "firstRun", "graphqlCost", "graphqlRemaining", "items"])
        self.assertTrue(b["firstRun"])
        self.assertEqual({i["number"]: i["mergeable"] for i in b["items"] if i["kind"] == "PR"}, {1: "MERGEABLE", 2: "UNKNOWN", 3: "CONFLICTING"})

    def test_the_data_folder_is_made_when_it_is_missing(self):
        self.assertFalse(os.path.exists(self.data))
        self.run_main()
        self.assertEqual(sorted(os.listdir(self.data)), ["board.html", "board.json", "stats.tsv"])

    def test_the_second_pull_keeps_the_first_as_prev_and_marks_what_is_new(self):
        self.run_main()
        first = self.board()
        self.assertEqual([i["new"] for i in first["items"]], [False] * 6)
        self.prs.append(pr_node(number=4))
        self.issues.append(issue_node(23))
        out = self.run_main()
        self.assertIn("2 new, ", out.splitlines()[0])
        self.assertNotIn("(first run)", out.splitlines()[0])
        second = self.board()
        self.assertFalse(second["firstRun"])
        self.assertEqual({(i["kind"], i["number"]) for i in second["items"] if i["new"]}, {("PR", 4), ("issue", 23)})
        self.assertEqual(self.board("board.prev.json"), first)

    def test_an_old_board_that_cannot_be_read_counts_as_the_first_run(self):
        for bad in ("{not json", '{"items": [{"x": 1}]}', "[]"):
            os.makedirs(self.data, exist_ok=True)
            with open(os.path.join(self.data, "board.json"), "w", encoding="utf-8") as fh:
                fh.write(bad)
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.run_main()
            self.assertTrue(self.board()["firstRun"], bad)
            self.assertIn("could not be read", err.getvalue())
            os.remove(os.path.join(self.data, "board.json"))

    def test_no_item_carries_a_mine_flag_and_no_search_is_made(self):
        self.run_main()
        for it in self.board()["items"]:
            self.assertNotIn("mine", it)
        queries = [c.args[0] for c in self.gql.call_args_list]
        self.assertTrue(queries)
        for q in queries:
            for word in ("search(", "author:", "commenter:"):
                self.assertNotIn(word, q)

    def test_the_keys_of_a_pr_item_and_an_issue_item(self):
        self.run_main()
        by_kind = {i["kind"]: i for i in self.board()["items"]}
        self.assertEqual(list(by_kind["PR"]), [
            "kind", "number", "title", "author", "association", "createdAt", "updatedAt", "labels", "url", "isDraft", "additions",
            "deletions", "changedFiles", "mergeable", "ci", "pushedAt", "closes", "namedInMain", "new", "sort", "why"])
        self.assertEqual(list(by_kind["issue"]), [
            "kind", "number", "title", "author", "association", "createdAt", "updatedAt", "labels", "url", "namedInMain", "new", "sort", "why"])

    def test_every_item_has_a_sort_that_is_a_lane_and_a_one_line_why(self):
        self.run_main()
        for it in self.board()["items"]:
            self.assertIn(it["sort"], lanes.PR_LANES if it["kind"] == "PR" else lanes.ISSUE_LANES, it)
            self.assertTrue(it["why"] and "\n" not in it["why"], it)
        got = {i["number"]: (i["sort"], i["why"]) for i in self.board()["items"]}
        self.assertEqual(got[20], ("plan", "author is a maintainer or plan author"))
        self.assertEqual(got[22], ("bug", 'has the label "bug"'))
        self.assertEqual(got[21], ("unsorted", "no sorting rule matched"))
        self.assertEqual(got[1][0], "flow")

    def test_the_title_is_sorted_and_no_query_or_item_has_a_body(self):
        self.issues[1] = issue_node(21, title="Seen on macOS only")
        self.run_main()
        for it in self.board()["items"]:
            self.assertNotIn("body", it)
        got = {i["number"]: (i["sort"], i["why"]) for i in self.board()["items"]}
        self.assertEqual(got[21], ("machine", "title mentions macOS"))
        for c in self.gql.call_args_list:
            self.assertNotIn("body", c.args[0])

    def test_an_open_pr_that_closes_an_issue_makes_it_inflight(self):
        self.prs[1] = pr_node(number=2, closes=(21,))
        self.run_main()
        got = {i["number"]: (i["sort"], i["why"]) for i in self.board()["items"]}
        self.assertEqual(got[21], ("inflight", "open PR #2 closes it"))

    def test_with_no_mirror_every_item_is_empty_and_no_git_command_runs(self):
        with mock.patch.object(pull.subprocess, "run") as run:
            out = self.run_main()
        run.assert_not_called()
        self.assertIn("named in main: no mirror set", out.splitlines()[0])
        items = self.board()["items"]
        self.assertEqual(len(items), 6)
        self.assertEqual([i["namedInMain"] for i in items], [[]] * 6)

    def test_with_a_mirror_the_items_it_names_get_the_commits_and_the_summary_counts_them(self):
        self.e.write_config({"data_dir": self.data, "mirror": "/path/to/rea.git"})
        with mock.patch.object(pull, "named_in_main", return_value={1: ["abc"], 3: ["def", "ghi"], 20: ["jkl"]}):
            out = self.run_main()
        self.assertIn(", 3 named in main, ", out.splitlines()[0])
        self.assertNotIn("no mirror", out)
        got = {(i["kind"], i["number"]): i["namedInMain"] for i in self.board()["items"]}
        self.assertEqual(got[("PR", 1)], ["abc"])
        self.assertEqual(got[("PR", 3)], ["def", "ghi"])
        self.assertEqual(got[("PR", 2)], [])
        self.assertEqual(got[("issue", 20)], ["jkl"])
        self.assertEqual(got[("issue", 21)], [])

    def test_with_a_mirror_an_issue_a_main_commit_names_is_landed_and_one_it_does_not_name_is_not(self):
        self.e.write_config({"data_dir": self.data, "mirror": "/path/to/rea.git", "maintainers": ["ann"], "plan_authors": ["cy"]})
        with mock.patch.object(pull, "named_in_main", return_value={21: ["abcdef1234"], 3: ["def"]}):
            out = self.run_main()
        self.assertIn(", 2 named in main, ", out.splitlines()[0])
        got = {(i["kind"], i["number"]): (i["sort"], i["why"]) for i in self.board()["items"]}
        self.assertEqual(got[("issue", 21)], ("landed", "commit abcdef1 on main mentions it"))
        self.assertEqual(got[("issue", 22)], ("bug", 'has the label "bug"'))
        self.assertEqual(got[("PR", 3)][0], "landed")

    def test_with_no_mirror_no_issue_is_landed(self):
        self.run_main()
        self.assertNotIn("landed", {i["sort"] for i in self.board()["items"] if i["kind"] == "issue"})

    def test_the_counts_are_printed_and_one_row_is_added_to_stats(self):
        out = self.run_main(now=STAMP)
        taken = STAMP.isoformat()
        self.assertEqual(self.board()["fetchedAt"], taken)
        want = lanes.count(self.board()["items"], STAMP, ["ann"], ["robo"])
        self.assertEqual(out.splitlines()[1:-2], lanes.report(want))
        self.assertRegex(out.splitlines()[-2], r"^board\.html: written, \d+\.\d KB$")
        self.assertEqual(out.splitlines()[-1], "stats.tsv: added a row for " + taken)
        self.assertEqual(self.stats(), [
            ["taken", "pr_flow", "pr_front", "pr_decide", "pr_landed", "pr_author", "pr_dead", "issue_plan", "issue_inflight", "issue_landed",
             "issue_ask", "issue_machine", "issue_sample", "issue_bug", "issue_unsorted"],
            [taken] + [str(want["prs"][k]) for k in lanes.PR_LANES] + [str(want["issues"][k]) for k in lanes.ISSUE_LANES]])
        self.assertEqual(want["prs"], {"flow": 1, "front": 0, "decide": 0, "landed": 0, "author": 1, "dead": 1})
        self.assertEqual(want["issues"], {"plan": 1, "inflight": 0, "landed": 0, "ask": 0, "machine": 0, "sample": 0, "bug": 1, "unsorted": 1})

    def test_the_page_is_written_right_after_the_board_from_the_same_items(self):
        self.issues[1]["title"] = "<script>alert(1)</script>"
        out = self.run_main(now=STAMP)
        self.assertIn("board.html: written, ", out)
        text = self.read("board.html")
        self.assertIn("Data from GitHub at 2026-11-14 12:00 UTC.", text)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", text)
        self.assertNotIn("<script", text)
        shown = [i for i in self.board()["items"] if (i["kind"], i["sort"]) not in board_page.LEFT_OUT]
        self.assertTrue(shown)
        self.assertEqual(text.count('<li class="card"'), len(shown))
        self.assertEqual(sum(int(n) for n in re.findall(r'<span class="count">(\d+)</span>', text)), len(shown))

    def test_the_second_pull_replaces_the_page(self):
        self.run_main(now=STAMP)
        self.run_main(now=datetime(2026, 11, 15, 12, 0, 0, tzinfo=timezone.utc))
        self.assertIn("Data from GitHub at 2026-11-15 12:00 UTC.", self.read("board.html"))
        self.assertEqual(sorted(os.listdir(self.data)), ["board.html", "board.json", "board.prev.json", "stats.tsv"])

    def test_a_page_that_cannot_be_written_stops_after_the_board_is_saved(self):
        os.makedirs(os.path.join(self.data, "board.html"))
        with self.assertRaises(SystemExit) as cm:
            self.run_main()
        self.assertIn("pull: cannot write", str(cm.exception))
        self.assertIn("board.html", str(cm.exception))
        self.assertEqual(len(self.board()["items"]), 6)
        self.assertFalse(os.path.exists(os.path.join(self.data, "stats.tsv")))

    def test_the_stats_row_is_added_once_for_each_fetched_at(self):
        self.run_main(now=STAMP)
        out = self.run_main(now=STAMP)
        self.assertEqual(out.splitlines()[-1], "stats.tsv: already has a row for " + STAMP.isoformat())
        self.assertEqual(len(self.stats()), 2)
        self.run_main(now=datetime(2026, 11, 15, 12, 0, 0, tzinfo=timezone.utc))
        self.assertEqual([r[0] for r in self.stats()], ["taken", STAMP.isoformat(), "2026-11-15T12:00:00+00:00"])

    def test_lanes_run_on_the_saved_board_adds_no_second_row(self):
        self.run_main(now=STAMP)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            lanes.main(["--board", os.path.join(self.data, "board.json"), "--append", os.path.join(self.data, "stats.tsv")])
        self.assertIn("already has a row for " + STAMP.isoformat(), out.getvalue())
        self.assertEqual(len(self.stats()), 2)

    def test_a_stats_file_that_cannot_be_written_stops_after_the_board_is_saved(self):
        os.makedirs(self.data)
        os.mkdir(os.path.join(self.data, "stats.tsv"))
        with self.assertRaises(SystemExit) as cm:
            self.run_main()
        self.assertIn("pull: cannot write", str(cm.exception))
        self.assertEqual(len(self.board()["items"]), 6)

    def test_a_stats_file_with_other_columns_stops_it_after_the_board_is_saved(self):
        os.makedirs(self.data)
        old = "taken\tflow\tfront\tdecide\tlanded\tauthor\tdead\tplan\tinflight\tsorted\tunsorted\n" + "2026-11-01T00:00:00+00:00" + "\t0" * 10 + "\n"
        with open(os.path.join(self.data, "stats.tsv"), "w", encoding="utf-8") as fh:
            fh.write(old)
        with self.assertRaises(SystemExit) as cm:
            self.run_main()
        self.assertNotEqual(cm.exception.code, 0)
        message = str(cm.exception)
        self.assertIn(os.path.join(self.data, "stats.tsv"), message)
        self.assertIn("move it aside", message)
        self.assertEqual(len(message.splitlines()), 1)
        self.assertEqual(len(self.board()["items"]), 6)
        self.assertEqual(self.read("stats.tsv"), old)


class EndToEndTest(unittest.TestCase):
    def setUp(self):
        self.e = FakeEnv().__enter__()
        self.addCleanup(self.e.__exit__)
        self.data = os.path.join(self.e.root, "data")
        self.e.write_config({"data_dir": self.data})

    def reply(self, key, nodes):
        return {"data": {"rateLimit": {"cost": 1, "remaining": 4990}, "repository": {key: page(nodes)}}}

    def run_pull(self, *args):
        return subprocess.run([sys.executable, "-I", PULL] + list(args), capture_output=True, text=True, stdin=subprocess.DEVNULL, env=dict(os.environ))

    def test_help_exits_zero_and_names_the_files(self):
        r = self.run_pull("--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("board.json", r.stdout)
        self.assertIn("board.html", r.stdout)
        self.assertIn("stats.tsv", r.stdout)

    def test_a_pull_with_no_arguments_does_the_whole_thing_through_gh_reads_only(self):
        self.e.gh_fixture("prs", match=r"pullRequests\(states", json=self.reply("pullRequests", [pr_node(number=1, author="morluto")]))
        self.e.gh_fixture("issues", match=r"issues\(states", json=self.reply("issues", [issue_node(20, author="matbrgz"), issue_node(21)]))
        r = self.run_pull()
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.splitlines()
        self.assertTrue(lines[0].startswith("1 PRs, 2 issues, 0 new (first run), named in main: no mirror set, 0 merge states unknown, "), lines[0])
        self.assertIn("graphql cost 2 (2 calls, 4990 left)", lines[0])
        self.assertIn("Pull requests: 1", lines)
        self.assertIn("  Maintainers' own and bots: 1", lines)
        self.assertIn("Issues: 2", lines)
        self.assertIn("  Maintainers' plan: 1", lines)
        self.assertIn("  Not sorted yet: 1", lines)
        self.assertTrue(lines[-2].startswith("board.html: written, "), lines[-2])
        self.assertTrue(lines[-1].startswith("stats.tsv: added a row for "))
        with open(os.path.join(self.data, "board.html"), encoding="utf-8") as fh:
            self.assertEqual(fh.read().count('<li class="card"'), 1)
        with open(os.path.join(self.data, "board.json"), encoding="utf-8") as fh:
            items = json.load(fh)["items"]
        self.assertEqual([(i["kind"], i["number"]) for i in items], [("PR", 1), ("issue", 20), ("issue", 21)])
        self.assertEqual([(i["sort"], i["why"]) for i in items][1:], [("plan", "author is a maintainer or plan author"), ("unsorted", "no sorting rule matched")])
        self.assertTrue(all("body" not in i for i in items))
        with open(os.path.join(self.data, "stats.tsv"), encoding="utf-8") as fh:
            self.assertEqual(len(fh.read().splitlines()), 2)
        calls = self.e.gh_calls()
        self.assertEqual(len(calls), 2)
        for c in calls:
            self.assertEqual(c[:3], ["api", "graphql", "-f"])
            self.assertTrue(c[3].startswith("query=query"))
            self.assertNotIn("body", c[3])
            for word in ("mutation", "search(", "author:", "commenter:"):
                self.assertNotIn(word, c[3])


if __name__ == "__main__":
    unittest.main()
