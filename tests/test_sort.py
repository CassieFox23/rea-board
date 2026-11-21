import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tests", "fakes"))
sys.path.insert(0, HERE)
from env import FakeEnv  # noqa: E402
import lanes  # noqa: E402
import sort  # noqa: E402

PLAN, UNSORTED = ["ann", "cy"], ["triage"]
DEFAULT_MAINT = ["morluto", "N0zoM1z0", "kaoru0822-kitauji", "baron"]


def issue(n=50, **kw):
    d = {"kind": "issue", "number": n, "title": "Something plain", "author": "dev", "labels": [], "namedInMain": []}
    d.update(kw)
    return d


def key(it, closed_by=None, plan=PLAN, unsorted=UNSORTED):
    return sort.issue_sort(it, closed_by or {}, plan, unsorted)[0]


def why(it, closed_by=None):
    return sort.issue_sort(it, closed_by or {}, PLAN, UNSORTED)[1]


class TagWordsTest(unittest.TestCase):
    def test_leading_tags_and_prefixes(self):
        self.assertEqual(sort.tag_words("[Bug] it breaks"), ["bug"])
        self.assertEqual(sort.tag_words("  [Bug][macOS] it breaks"), ["bug", "macos"])
        self.assertEqual(sort.tag_words("[RFC/Epic] a plan"), ["rfc", "epic"])
        self.assertEqual(sort.tag_words("[Provider proposal] a plan"), ["provider", "proposal"])
        self.assertEqual(sort.tag_words("fix: it breaks"), ["fix"])
        self.assertEqual(sort.tag_words("Feat(parser)!: more"), ["feat", "parser"])
        self.assertEqual(sort.tag_words("[Feature] fix: more"), ["feature", "fix"])

    def test_a_tag_that_is_not_leading_is_not_one(self):
        self.assertEqual(sort.tag_words("It breaks [Bug]"), [])
        self.assertEqual(sort.tag_words("Support for windows: yes"), [])
        self.assertEqual(sort.tag_words("array[0] is wrong"), [])
        self.assertEqual(sort.tag_words(""), [])


class PlanTest(unittest.TestCase):
    def test_a_plan_author_wrote_it(self):
        self.assertEqual(sort.issue_sort(issue(author="ann"), {}, PLAN, UNSORTED), ("plan", "author is a maintainer or plan author"))
        self.assertEqual(key(issue(author="CY")), "plan")
        self.assertEqual(key(issue(author="dev")), "unsorted")
        self.assertEqual(key(issue(author=None)), "unsorted")

    def test_the_roadmap_label(self):
        self.assertEqual(sort.issue_sort(issue(labels=["roadmap"]), {}, PLAN, UNSORTED), ("plan", 'has the label "roadmap"'))
        self.assertEqual(key(issue(labels=["Roadmap"])), "plan")

    def test_plan_tags(self):
        for title in ("[Tracker] x", "[Epic] x", "[RFC/Epic] x", "[Roadmap] x", "[Governance] x", "Epic: x"):
            self.assertEqual(key(issue(title=title)), "plan", title)
        self.assertEqual(why(issue(title="[RFC/Epic] x")), "title contains [epic]")
        self.assertEqual(key(issue(title="[RFC] x")), "ask")

    def test_plan_beats_every_rule_but_inflight(self):
        it = issue(10, author="ann", title="[Bug] macOS", labels=["bug", "enhancement"], namedInMain=["abc1234"])
        self.assertEqual(key(it), "plan")
        self.assertEqual(key(it, closed_by={10: [3]}), "inflight")
        it = issue(10, title="[Epic] x", labels=["bug"], namedInMain=["abc1234"])
        self.assertEqual(key(it), "plan")
        self.assertEqual(key(it, closed_by={10: [3]}), "inflight")


class InflightTest(unittest.TestCase):
    def test_an_open_pr_that_closes_it(self):
        self.assertEqual(sort.issue_sort(issue(50), {50: [9, 7]}, PLAN, UNSORTED), ("inflight", "open PR #7 closes it"))
        self.assertEqual(key(issue(50), closed_by={51: [7], 52: [8]}), "unsorted")
        self.assertEqual(key(issue(50), closed_by={50: []}), "unsorted")
        self.assertEqual(key(issue(50), closed_by={}), "unsorted")

    def test_inflight_beats_landed_ask_machine_sample_and_bug(self):
        it = issue(50, title="[Bug] macOS crash sample file", labels=["bug", "enhancement"], namedInMain=["abc1234"])
        self.assertEqual(key(it, closed_by={50: [3]}), "inflight")


class LandedTest(unittest.TestCase):
    def test_a_main_commit_names_it(self):
        self.assertEqual(sort.issue_sort(issue(namedInMain=["abcdef1234567"]), {}, PLAN, UNSORTED), ("landed", "commit abcdef1 on main mentions it"))
        self.assertEqual(key(issue(namedInMain=["abc", "def"])), "landed")

    def test_no_commit_or_no_key_means_no_landing(self):
        self.assertEqual(key(issue(namedInMain=[])), "unsorted")
        d = issue()
        del d["namedInMain"]
        self.assertEqual(key(d), "unsorted")

    def test_landed_beats_ask_machine_sample_and_bug(self):
        it = issue(title="[Feature] macOS crash sample file", labels=["bug", "enhancement"], namedInMain=["abc1234"])
        self.assertEqual(key(it), "landed")


class AskTest(unittest.TestCase):
    def test_ask_tags(self):
        for title in ("[Feature] x", "[Feat] x", "[Design] x", "[Docs] x", "[Proposal] x", "[RFC] x", "[Question] x", "[Research] x",
                      "[Provider proposal] x", "[RFC/Feature] x", "feat: x", "docs: x", "proposal: x", "research: x"):
            self.assertEqual(key(issue(title=title)), "ask", title)
        self.assertEqual(why(issue(title="[Provider proposal] x")), "title contains [proposal]")

    def test_ask_labels(self):
        for label in ("enhancement", "design", "documentation", "question", "provider-request"):
            self.assertEqual(sort.issue_sort(issue(labels=[label]), {}, PLAN, UNSORTED), ("ask", 'has the label "%s"' % label), label)
        self.assertEqual(key(issue(labels=["Enhancement"])), "ask")

    def test_a_tag_is_named_before_a_label(self):
        self.assertEqual(why(issue(title="[Feature] x", labels=["enhancement"])), "title contains [feature]")

    def test_other_labels_do_not_make_an_ask(self):
        for label in ("area:evidence", "P1: high", "performance", "i18n"):
            self.assertEqual(key(issue(labels=[label])), "unsorted", label)

    def test_ask_beats_machine_sample_and_bug_words(self):
        self.assertEqual(key(issue(title="[Feature] macOS crash sample file", labels=["enhancement"])), "ask")

    def test_a_bug_label_beats_an_ask_signal(self):
        self.assertEqual(sort.issue_sort(issue(labels=["bug", "enhancement"]), {}, PLAN, UNSORTED), ("bug", 'has the label "bug"'))
        self.assertEqual(key(issue(labels=["enhancement", "design", "bug"])), "bug")
        self.assertEqual(key(issue(title="[Feature] x", labels=["bug"])), "bug")

    def test_a_bug_tag_beats_an_ask_signal(self):
        self.assertEqual(sort.issue_sort(issue(title="[Bug] x", labels=["enhancement"]), {}, PLAN, UNSORTED), ("bug", "title contains [bug]"))
        self.assertEqual(key(issue(title="fix: x", labels=["enhancement", "design"])), "bug")
        self.assertEqual(key(issue(title="[Design] [Bug] x")), "bug")
        self.assertEqual(key(issue(title="[Bug] x", labels=["documentation", "question", "provider-request"])), "bug")

    def test_a_title_that_opens_with_a_feature_verb(self):
        for title in ("Add a thing", "allow it to run", "Support more things", "Improve the output", "Expose the field", "Implement it",
                      "Provide a flag", "Enable the mode", "Document the flags", "Propose a change", "[Foo] Add a thing", "chore: add a thing"):
            self.assertEqual(key(issue(title=title)), "ask", title)
        self.assertEqual(why(issue(title="[Foo] Add a thing")), 'title starts with "add"')
        for title in ("Adding a thing", "Address the thing", "Supports it", "The add button", "x add"):
            self.assertEqual(key(issue(title=title)), "unsorted", title)

    def test_a_title_that_is_a_question(self):
        self.assertEqual(sort.issue_sort(issue(title="Would you accept a thing?"), {}, PLAN, UNSORTED), ("ask", "title is a question"))
        self.assertEqual(key(issue(title="Would you accept a thing? ")), "ask")
        self.assertEqual(key(issue(title="Would you accept a thing")), "unsorted")
        self.assertEqual(key(issue(title="Is it a [Bug]? yes")), "unsorted")

    def test_a_bug_signal_beats_the_title_words_too(self):
        self.assertEqual(key(issue(title="Add a thing", labels=["bug"])), "bug")
        self.assertEqual(key(issue(title="[Bug] Add a thing")), "bug")
        self.assertEqual(key(issue(title="Is it broken?", labels=["bug"])), "bug")

    def test_a_bug_word_alone_does_not_beat_an_ask(self):
        self.assertEqual(key(issue(title="Crash report page", labels=["enhancement"])), "ask")


class MachineTest(unittest.TestCase):
    def test_words_in_the_title(self):
        for word in ("macOS", "Mac OS", "OSX", "Apple silicon", "Windows", "iOS", "iPadOS", "iPhone", "iPad", "Xcode", "Hopper", "JEB",
                     "IDA Pro", "Binary Ninja", "real device", "physical device", "Android device"):
            self.assertEqual(key(issue(title="Run it on %s please" % word)), "machine", word)
        self.assertEqual(why(issue(title="Run it on macOS please")), "title mentions macOS")
        self.assertEqual(why(issue(title="needs IDA pro")), "title mentions IDA pro")

    def test_whole_words_only(self):
        for title in ("Radios are loud", "Visit Idaho", "The windowsill", "Aios", "Jebediah", "Hoppers", "Mac OSes"):
            self.assertEqual(key(issue(title=title)), "unsorted", title)

    def test_a_title_word_beats_a_bug_signal_and_the_sample_words(self):
        self.assertEqual(key(issue(title="macOS crash sample file", labels=["bug"])), "machine")
        self.assertEqual(key(issue(title="[Bug] macOS crash")), "machine")
        self.assertEqual(key(issue(title="macOS crash")), "machine")

    def test_machine_beats_sample_wherever_the_words_stand(self):
        self.assertEqual(key(issue(title="On macOS, attach the binary")), "machine")
        self.assertEqual(key(issue(title="attach the binary, on macOS")), "machine")


class SampleTest(unittest.TestCase):
    def test_words_in_the_title(self):
        self.assertEqual(sort.issue_sort(issue(title="Fails on this sample file"), {}, PLAN, UNSORTED), ("sample", "title mentions sample file"))

    def test_every_word(self):
        for words in ("sample file", "sample binary", "sample apk", "attach the binary", "attach the file", "attach a sample",
                      "attach a binary", "attached binary", "attached sample", "upload the binary", "upload a sample",
                      "share the binary", "share a sample", "test binary"):
            self.assertEqual(sort.issue_sort(issue(title="Please " + words + ", thanks"), {}, PLAN, UNSORTED), ("sample", "title mentions " + words), words)

    def test_a_title_word_beats_a_bug_signal(self):
        self.assertEqual(key(issue(title="Fails on this sample file", labels=["bug"])), "sample")
        self.assertEqual(key(issue(title="[Bug] sample file")), "sample")
        self.assertEqual(key(issue(title="Crash on parse, attach the binary")), "sample")


class BugTest(unittest.TestCase):
    def test_the_label(self):
        self.assertEqual(sort.issue_sort(issue(labels=["bug"]), {}, PLAN, UNSORTED), ("bug", 'has the label "bug"'))
        self.assertEqual(key(issue(labels=["Bug", "area:native"])), "bug")

    def test_the_tags(self):
        for title in ("[Bug] x", "[bug] x", "fix: x", "Fix(parser): x", "[Bugfix] x", "[Regression] x"):
            self.assertEqual(key(issue(title=title)), "bug", title)

    def test_words_in_the_title(self):
        for title in ("It crashes on start", "Parser fails", "Error when opening", "Unhandled exception", "Output is wrong", "Hangs forever",
                      "Segfault in the loader", "Traceback on exit", "Export not working", "Cannot open it", "Unable to load it",
                      "Regression in 2.0", "Broken link"):
            self.assertEqual(key(issue(title=title)), "bug", title)
        self.assertEqual(why(issue(title="It crashes on start")), 'title contains the word "crashes"')

    def test_bug_words_need_a_word_start(self):
        self.assertEqual(key(issue(title="Overhang style")), "unsorted")
        self.assertEqual(key(issue(title="Preerror")), "unsorted")


class UnsortedTest(unittest.TestCase):
    def test_nothing_matched(self):
        self.assertEqual(sort.issue_sort(issue(), {}, PLAN, UNSORTED), ("unsorted", "no sorting rule matched"))
        self.assertEqual(key(issue(labels=["area:evidence", "P2: medium"])), "unsorted")
        d = issue()
        del d["labels"]
        del d["title"]
        self.assertEqual(key(d), "unsorted")

    def test_the_body_is_never_read(self):
        self.assertEqual(key(issue(body="Only on macOS and Windows. Attach the binary. It crashes with an error.")), "unsorted")

    def test_triage_is_not_a_signal(self):
        self.assertEqual(key(issue(labels=["triage"])), "unsorted")
        self.assertEqual(key(issue(labels=["Triage"])), "unsorted")
        self.assertEqual(key(issue(labels=["triage", "enhancement"])), "ask")
        self.assertEqual(key(issue(labels=["triage", "bug"])), "bug")

    def test_a_label_in_unsorted_labels_is_ignored_whatever_it_is(self):
        it = issue(labels=["enhancement"])
        self.assertEqual(key(it, unsorted=["triage"]), "ask")
        self.assertEqual(key(it, unsorted=["triage", "Enhancement"]), "unsorted")
        self.assertEqual(key(issue(labels=["bug", "enhancement"]), unsorted=["bug"]), "ask")


class OrderTest(unittest.TestCase):
    def test_first_match_wins(self):
        it = issue(10, author="ann", title="[Epic] [Bug] macOS crash", labels=["roadmap", "bug", "enhancement"], namedInMain=["abc1234"])
        self.assertEqual(key(it, {10: [3]}), "inflight")
        self.assertEqual(key(it), "plan")
        it = dict(it, author="dev", title="[Bug] macOS crash", labels=["bug", "enhancement"])
        self.assertEqual(key(it, {10: [3]}), "inflight")
        self.assertEqual(key(it), "landed")
        it = dict(it, namedInMain=[])
        self.assertEqual(key(it), "machine")
        it = dict(it, title="[Bug] sample file")
        self.assertEqual(key(it), "sample")
        it = dict(it, title="[Bug] x")
        self.assertEqual(key(it), "bug")
        self.assertEqual(key(dict(it, labels=[], title="crash")), "bug")
        it = dict(it, title="x", labels=["enhancement"])
        self.assertEqual(key(it), "ask")
        self.assertEqual(key(dict(it, labels=[])), "unsorted")

    def test_every_key_is_a_lane_and_every_why_is_one_line(self):
        for it in (issue(author="ann"), issue(labels=["enhancement"]), issue(labels=["bug"]), issue(title="macOS"), issue(namedInMain=["abc"]),
                   issue(title="[Epic] x"), issue(title="a sample file"), issue(title="Add x"), issue()):
            k, w = sort.issue_sort(it, {}, PLAN, UNSORTED)
            self.assertIn(k, lanes.ISSUE_LANES)
            self.assertTrue(w and "\n" not in w, w)
        self.assertEqual(lanes.ISSUE_LANES, ("plan", "inflight", "landed", "ask", "machine", "sample", "bug", "unsorted"))


class ConfigTest(unittest.TestCase):
    def test_with_no_config_file_the_defaults_apply(self):
        with FakeEnv():
            self.assertEqual(sort.config(), (DEFAULT_MAINT + ["matbrgz"], ["triage"]))

    def test_the_plan_set_is_the_maintainers_and_plan_authors(self):
        with FakeEnv({"maintainers": ["ann", "bo"], "plan_authors": ["cy"], "unsorted_labels": ["triage", "needs info"]}):
            self.assertEqual(sort.config(), (["ann", "bo", "cy"], ["triage", "needs info"]))


if __name__ == "__main__":
    unittest.main()
