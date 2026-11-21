"""Sort one open issue by what it needs, first match wins: inflight, plan, landed, ask, machine, sample, bug, unsorted.

issue_sort gives (key, why): the key is one of lanes.ISSUE_LANES, the why a short line naming the rule and what matched.
Case does not matter. A label in unsorted_labels (triage) is not a signal for anything. A bug signal (the bug label, or a
[Bug] or fix: tag) keeps an issue out of ask. An issue's body is never read.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conf  # noqa: E402

PLAN_LABELS = ("roadmap",)
PLAN_TAGS = ("tracker", "epic", "roadmap", "governance")
ASK_LABELS = ("enhancement", "design", "documentation", "question", "provider-request")
ASK_TAGS = ("feature", "feat", "design", "docs", "proposal", "rfc", "question", "research")
ASK_VERBS = ("add", "allow", "support", "improve", "expose", "implement", "provide", "enable", "document", "propose")
BUG_LABELS = ("bug",)
BUG_TAGS = ("bug", "fix", "bugfix", "regression")
MACHINE_WORDS = ("macos", "mac os", "osx", "apple silicon", "windows", "ios", "ipados", "iphone", "ipad", "xcode", "hopper",
                 "jeb", "ida pro", "binary ninja", "real device", "physical device", "android device")
SAMPLE_WORDS = ("sample file", "sample binary", "sample apk", "attach the binary", "attach the file", "attach a sample",
                "attach a binary", "attached binary", "attached sample", "upload the binary", "upload a sample",
                "share the binary", "share a sample", "test binary")
BUG_WORDS = ("crash", "fail", "error", "exception", "broken", "regress", "wrong", "incorrect", "hang", "freez", "segfault",
             "panic", "traceback", "not working", "cannot", "unable to")
LEAD = re.compile(r"\s*(?:\[[^\]]*\]\s*)*(?:\w+(?:\([^)]*\))?!?:)?")


def listed(words, tail=""):
    return re.compile(r"\b(?:%s)%s" % ("|".join(re.escape(w) for w in words), tail), re.IGNORECASE)


MACHINE, SAMPLE, BUGGY = listed(MACHINE_WORDS, r"\b"), listed(SAMPLE_WORDS, r"\b"), listed(BUG_WORDS, r"\w*")


def tag_words(title):
    """The lower-case words of a title's leading [tags], and of a leading fix: or feat(scope): prefix."""
    return re.findall(r"\w+", LEAD.match(title).group().lower())


def signal(labels, tags, want_labels, want_tags):
    """A why for the first tag, else the first label, that is wanted; None when neither is."""
    for t in tags:
        if t in want_tags:
            return "title contains [%s]" % t
    for l in labels:
        if l in want_labels:
            return 'has the label "%s"' % l
    return None


def title_ask(title):
    """A why when the title is a question or opens with a feature verb, after any tags; else None."""
    rest = title[LEAD.match(title).end():].strip()
    first = re.match(r"\w+", rest)
    if first and first.group().lower() in ASK_VERBS:
        return 'title starts with "%s"' % first.group().lower()
    return "title is a question" if rest.endswith("?") else None


def needs(title):
    """(key, why) for the first of machine, sample whose words are in the title; None when neither is."""
    for key, words in (("machine", MACHINE), ("sample", SAMPLE)):
        m = words.search(title)
        if m:
            return key, "title mentions " + m.group()
    return None


def names(words):
    return {str(w).lower() for w in words}


def issue_sort(item, closed_by, plan_authors, unsorted_labels):
    """(key, why) of one issue. closed_by maps an issue number to the open PRs that close it; plan_authors is the whole plan set."""
    title = item.get("title") or ""
    skip = names(unsorted_labels)
    labels = [str(l).lower() for l in item.get("labels") or [] if str(l).lower() not in skip]
    tags = tag_words(title)
    if closed_by.get(item.get("number")):
        return "inflight", "open PR #%d closes it" % min(closed_by[item["number"]])
    if str(item.get("author") or "").lower() in names(plan_authors):
        return "plan", "author is a maintainer or plan author"
    plan = signal(labels, tags, PLAN_LABELS, PLAN_TAGS)
    if plan:
        return "plan", plan
    if item.get("namedInMain"):
        return "landed", "commit %s on main mentions it" % item["namedInMain"][0][:7]
    bug = signal(labels, tags, BUG_LABELS, BUG_TAGS)
    ask = signal(labels, tags, ASK_LABELS, ASK_TAGS) or title_ask(title)
    if ask and not bug:
        return "ask", ask
    got = needs(title)
    if got:
        return got
    if bug:
        return "bug", bug
    m = BUGGY.search(title)
    if m:
        return "bug", 'title contains the word "%s"' % m.group().lower()
    return "unsorted", "no sorting rule matched"


def config():
    """(plan_authors, unsorted_labels) from config; the plan set is the maintainers and plan_authors."""
    return conf.maintainers() + conf.plan_authors(), conf.unsorted_labels()
