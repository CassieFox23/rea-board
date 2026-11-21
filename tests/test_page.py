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

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tests", "fakes"))
sys.path.insert(0, HERE)
from env import FakeEnv  # noqa: E402

import lanes  # noqa: E402
import page  # noqa: E402

PAGE = os.path.join(HERE, "page.py")
TAKEN = datetime(2026, 11, 14, 22, 56, 44, tzinfo=timezone.utc)
PALETTE = {
    "#1e1e2e": (30, 30, 46), "#181825": (24, 24, 37), "#313244": (49, 50, 68), "#45475a": (69, 71, 90),
    "#c6d0f5": (198, 208, 245), "#a6adc8": (166, 173, 200), "#9399b2": (147, 153, 178), "#7f849c": (127, 132, 156),
    "#cba6f7": (203, 166, 247), "#89b4fa": (137, 180, 250), "#f38ba8": (243, 139, 168), "#a6e3a1": (166, 227, 161),
    "#fab387": (250, 179, 135), "#f9e2af": (249, 226, 175), "#94e2d5": (148, 226, 213), "#eba0ac": (235, 160, 172),
    "#b4befe": (180, 190, 254), "#f2cdcd": (242, 205, 205), "#f5e0dc": (245, 224, 220),
}
ALL_PAIRS = [("PR", k) for k in lanes.PR_LANES] + [("issue", k) for k in lanes.ISSUE_LANES]


def item(kind="issue", number=1, sort="unsorted", **more):
    out = {"kind": kind, "number": number, "title": "title %s" % number, "author": "a", "createdAt": "2026-11-01T00:00:00Z",
           "updatedAt": "2026-11-02T00:00:00Z", "labels": [], "url": "https://github.com/morluto/rea/issues/%s" % number,
           "namedInMain": [], "new": False, "sort": sort, "why": "why %s" % number}
    if kind == "PR":
        out.update(isDraft=False, mergeable="MERGEABLE", ci="SUCCESS", pushedAt="2026-11-02T00:00:00Z", closes=[])
    out.update(more)
    return {k: v for k, v in out.items() if v is not None}


def every_pair():
    return [item(k, n, s) for n, (k, s) in enumerate(ALL_PAIRS, 1)]


def counts(text):
    """The count pill of each column, in page order."""
    return [int(n) for n in re.findall(r'<span class="count">(\d+)</span>', text)]


def columns(text):
    """The column sections of the page, in order."""
    return re.findall(r'<section class="column">.*?</section>', text, re.S)


def numbers(section):
    """The item numbers of the cards in one column, in page order."""
    return [int(n) for n in re.findall(r'<span class="num">#(\d+)</span>', section)]


def style(text):
    return re.search(r"<style>(.*?)</style>", text, re.S).group(1)


class SetUp(unittest.TestCase):
    def setUp(self):
        self.e = FakeEnv().__enter__()
        self.addCleanup(self.e.__exit__)


class TablesTest(SetUp):
    def test_the_columns_in_order(self):
        self.assertEqual([c[0] for c in page.COLUMNS], ["Not sorted yet", "Review or test", "Fix a bug", "Ideas and questions", "Maybe already fixed"])

    def test_the_pairs_that_make_no_card(self):
        self.assertEqual(page.LEFT_OUT, (("PR", "author"), ("PR", "dead"), ("PR", "flow"), ("issue", "plan"), ("issue", "inflight")))

    def test_every_pair_is_held_once_by_a_column_or_left_out(self):
        held = [p for c in page.COLUMNS for p in c[2]] + list(page.LEFT_OUT)
        self.assertEqual(sorted(held), sorted(ALL_PAIRS))

    def test_each_column_has_a_title_and_a_short_line_on_what_to_do(self):
        self.assertEqual(len({c[0] for c in page.COLUMNS}), len(page.COLUMNS))
        for title, todo, pairs in page.COLUMNS:
            self.assertTrue(title and todo and pairs, title)
            self.assertLess(len(todo), 200, title)


class GroupTest(SetUp):
    def test_each_pair_lands_in_the_column_that_holds_it_or_makes_no_card(self):
        got = page.group(every_pair())
        self.assertEqual(len(got), len(page.COLUMNS))
        for n, (title, todo, pairs) in enumerate(page.COLUMNS):
            self.assertEqual(sorted((i["kind"], i["sort"]) for i in got[n]), sorted(pairs), title)
        text = page.render(every_pair(), TAKEN)
        for n, (title, todo, pairs) in enumerate(page.COLUMNS):
            self.assertEqual(len(numbers(columns(text)[n])), len(pairs), title)
        self.assertEqual(text.count('<li class="card"'), sum(len(c[2]) for c in page.COLUMNS))
        for p in page.LEFT_OUT:
            self.assertIsNone(page.column_of(item(p[0], 1, p[1])), p)

    def test_an_unknown_pair_lands_in_sort_it(self):
        items = [item("issue", 1, None), item("PR", 2, None), item("issue", 3, "gibberish"), item("PR", 4, "unsorted"),
                 item("issue", 5, "front"), item("issue", 6, ["bug"]), item("epic", 7, "bug"), item(None, 8, "ask")]
        got = page.group(items)
        self.assertEqual([i["number"] for i in got[0]], [1, 2, 3, 4, 5, 6, 7, 8])
        self.assertEqual(sum(len(c) for c in got[1:]), 0)
        self.assertEqual(counts(page.render(items, TAKEN)), [8, 0, 0, 0, 0])

    def test_a_left_out_item_never_goes_to_the_fallback(self):
        items = [item("PR", 1, "author"), item("PR", 2, "dead"), item("PR", 3, "flow"), item("issue", 4, "plan"), item("issue", 5, "inflight")]
        self.assertEqual(page.group(items), [[]] * len(page.COLUMNS))
        self.assertNotIn('<li class="card"', page.render(items, TAKEN))

    def test_oldest_first_and_an_item_with_no_time_last(self):
        items = [item(number=1, createdAt="2026-11-10T00:00:00Z"), item(number=2, createdAt="2026-01-01T00:00:00Z"),
                 item(number=3, createdAt=None), item(number=4, createdAt="not a time"), item(number=5, createdAt="2026-06-01T00:00:00Z")]
        self.assertEqual([i["number"] for i in page.group(items)[0]], [2, 5, 1, 3, 4])
        self.assertEqual(numbers(columns(page.render(items, TAKEN))[0]), [2, 5, 1, 3, 4])

    def test_two_tables_of_pairs_share_a_column_oldest_first(self):
        items = [item("issue", 1, "machine", createdAt="2026-11-05T00:00:00Z"), item("issue", 2, "bug", createdAt="2026-11-03T00:00:00Z"),
                 item("issue", 3, "sample", createdAt="2026-11-04T00:00:00Z")]
        self.assertEqual(numbers(columns(page.render(items, TAKEN))[2]), [2, 3, 1])


class RenderTest(SetUp):
    def test_an_empty_board_renders_every_column_with_a_zero_and_the_empty_text(self):
        text = page.render([], TAKEN)
        self.assertEqual(counts(text), [0] * len(page.COLUMNS))
        self.assertEqual(len(columns(text)), len(page.COLUMNS))
        self.assertEqual(text.count("No items in this column."), len(page.COLUMNS))
        self.assertNotIn('<li class="card"', text)
        self.assertNotIn('<ul class="cards">', text)
        self.assertIn('Showing <span class="mono">%s</span> of <span class="mono">%s</span> open pull requests and issues.' % (0, 0), text)

    def test_a_column_with_cards_has_no_empty_text(self):
        text = page.render([item("PR", 1, "front")], TAKEN)
        self.assertNotIn("No items in this column.", columns(text)[1])
        self.assertEqual(text.count("No items in this column."), len(page.COLUMNS) - 1)

    def test_the_header(self):
        text = page.render([item("PR", 1, "front"), item("PR", 2, "author"), item("issue", 3)], TAKEN)
        self.assertIn("<h1>rea-board</h1>", text)
        self.assertIn('<p class="about">Open pull requests and issues on <a href="https://github.com/morluto/rea">morluto/rea</a>, '
                      'grouped by the kind of help each one needs.</p>', text)
        self.assertNotIn("quest board", text.lower())
        self.assertIn("Data from GitHub at 2026-11-14 22:56 UTC.", text)
        self.assertIn('Showing <span class="mono">%s</span> of <span class="mono">%s</span> open pull requests and issues.' % (2, 3), text)
        self.assertNotIn("Also open", text)
        self.assertNotIn("Waiting on the author", text)

    def test_the_header_counts_the_cards_out_of_every_item(self):
        items = ([item("PR", n, "author") for n in range(1, 4)] + [item("PR", 4, "dead")] + [item("PR", 5, "flow")] +
                 [item("issue", n, "plan") for n in range(6, 8)] + [item("issue", 8, "inflight")] + [item("PR", 9, "front")])
        self.assertIn('Showing <span class="mono">%s</span> of <span class="mono">%s</span> open pull requests and issues.' % (1, 9), page.render(items, TAKEN))
        many = [item("issue", n, "plan") for n in range(1, 1373)] + [item("issue", 1373, "bug")]
        self.assertIn('Showing <span class="mono">%s</span> of <span class="mono">%s</span> open pull requests and issues.' % (1, "1,373"), page.render(many, TAKEN))

    def test_the_count_pills_and_the_totals_cover_every_item(self):
        text = page.render(every_pair(), TAKEN)
        self.assertEqual(sum(counts(text)) + len(page.LEFT_OUT), len(ALL_PAIRS))
        self.assertIn('Showing <span class="mono">%s</span> of <span class="mono">%s</span> open pull requests and issues.' % (sum(counts(text)), len(ALL_PAIRS)), text)

    def test_a_column_header_has_the_title_the_count_and_what_to_do(self):
        text = page.render([item("PR", 12, "front", title="Fix it", createdAt="2026-11-11T22:00:00Z", why="CI passing, opened under 3 days ago")], TAKEN)
        self.assertIn('<h2>Review or test</h2><span class="count">1</span>', text)
        self.assertIn('<p class="todo">All CI checks pass and there are no merge conflicts. Read the code change, or test it and comment with the result.</p>', text)
        self.assertIn('<p class="todo">The board could not tell from the title or labels whether each item is a bug, an idea or a question. Open one '
                      'on GitHub and comment which it is, so a maintainer can add a label.</p>', text)
        self.assertNotIn("script", re.sub(r"<style>.*?</style>", "", text).lower())
        self.assertIn('<p class="todo">Bug reports. Reproduce a bug, then fix it. Some need a sample file, a Mac, a Windows PC or a paid tool.</p>', text)
        self.assertIn('<p class="todo">Feature requests, design proposals and questions. Answer a question, or comment on a request with more detail.</p>', text)
        self.assertIn('<p class="todo">A commit on main mentions these items. Check whether the commit fixed each one, then comment on the item to say if it is fixed.</p>', text)
        self.assertIn('<p class="title"><a href="https://github.com/morluto/rea/issues/12">Fix it</a></p>', text)
        self.assertIn('<span class="tag green">CI passing</span><span class="num">#12</span></div>', text)
        self.assertIn('<p class="meta"><span class="age">Opened 3 days ago</span><span class="why">CI passing, opened under 3 days ago</span></p>', text)

    def test_the_age_words(self):
        for created, want in (("2026-11-14T22:00:00Z", "Opened today"), ("2026-11-13T22:00:00Z", "Opened 1 day ago"), ("2026-11-12T22:57:00Z", "Opened 1 day ago"),
                              ("2026-11-12T22:56:00Z", "Opened 2 days ago"), ("2026-08-16T00:00:00Z", "Opened 90 days ago"), ("2026-12-01T00:00:00Z", "Opened today")):
            self.assertIn('<span class="age">%s</span>' % want, page.render([item(createdAt=created)], TAKEN), created)
        self.assertNotIn('class="age"', page.render([item(createdAt=None)], TAKEN))
        self.assertNotIn('class="age"', page.render([item(createdAt="not a time")], TAKEN))

    def test_a_card_starts_with_its_label_chips(self):
        def tags(**more):
            text = page.render([item("PR", 1, "front", **more)], TAKEN)
            return re.findall(r'<span class="tag (\w+)">(.*?)</span>', re.search(r'<div class="tags">(.*?)</div>', text).group(1))
        self.assertEqual(tags(), [("lavender", "PR"), ("green", "CI passing")])
        self.assertEqual(tags(isDraft=True, mergeable="CONFLICTING", ci="FAILURE"),
                         [("lavender", "PR"), ("soft", "draft"), ("peach", "merge conflict"), ("red", "CI failing")])
        self.assertEqual(tags(ci="ERROR")[-1], ("red", "CI failing"))
        self.assertEqual(tags(ci="PENDING")[-1], ("yellow", "CI running"))
        self.assertEqual(tags(ci="EXPECTED")[-1], ("yellow", "CI running"))
        self.assertEqual(tags(ci=None)[-1], ("soft", "no checks ran"))
        self.assertEqual(tags(ci="ODD")[-1], ("soft", "CI odd"))
        self.assertEqual(tags(mergeable="UNKNOWN")[-1], ("green", "CI passing"))

    def test_an_issue_has_its_kind_and_the_need_its_sort_names_and_no_pr_chips(self):
        def tags(sort, **more):
            text = page.render([item("issue", 1, sort, **more)], TAKEN)
            return [w for _, w in re.findall(r'<span class="tag (\w+)">(.*?)</span>', text)]
        self.assertEqual(tags("bug", isDraft=True, ci="FAILURE", mergeable="CONFLICTING"), ["Issue"])
        self.assertEqual(tags("ask"), ["Issue"])
        self.assertEqual(tags("sample"), ["Issue", "needs a sample file"])
        self.assertEqual(tags("machine"), ["Issue", "needs a Mac, a Windows PC or a paid tool"])

    def test_a_compact_card_is_chips_and_number_then_title_then_age_and_why(self):
        text = page.render([item("PR", 1, "front")], TAKEN)
        order = [text.index(w) for w in ('class="tags"', 'class="num"', 'class="title"', 'class="meta"', 'class="age"', 'class="why"')]
        self.assertEqual(order, sorted(order))
        self.assertNotIn('class="foot"', text)
        self.assertEqual(text.count("<p "), text.count("<p class=\"todo\">") + text.count("<p class=\"empty\">") + 4)

    def test_there_is_no_filter_bar_and_cards_carry_no_filter_marks(self):
        text = page.render([item("PR", 1, "front"), item("PR", 2, "landed", isDraft=True), item("issue", 3, "ask")], TAKEN)
        for gone in ('class="filters"', "data-kind", "data-draft", 'type="checkbox"'):
            self.assertNotIn(gone, text)
        self.assertEqual(text.count('<li class="card" '), 3)

    def test_the_sort_buttons_are_three_radios_and_the_css_that_orders_the_cards(self):
        text = page.render([], TAKEN)
        self.assertIn('<div class="sorts" role="group" aria-label="Sort the cards">', text)
        self.assertEqual(re.findall(r'<label class="pill"><input type="radio" name="sort" id="([\w-]+)"( checked)?>([^<]*)</label>', text), [
            ("s-old", " checked", "Oldest first"), ("s-new", "", "Newest first"), ("s-upd", "", "Recently updated")])
        css = style(text)
        self.assertIn("body:has(#s-new:checked) .card{order:var(--new)}", css)
        self.assertIn("body:has(#s-upd:checked) .card{order:var(--upd)}", css)
        self.assertIn(".pill input{position:absolute;opacity:0;", css)
        self.assertIn(".pill:has(input:focus-visible)", css)
        self.assertLess(text.index('class="sorts"'), text.index('<main class="board">'))

    def test_the_scrollbars_are_thin_and_dim_and_pass_3_to_1(self):
        self.assertIn(".board,.cards{scrollbar-width:thin;scrollbar-color:#7f849c transparent}", style(page.render([], TAKEN)))

    def test_the_small_grey_text_on_a_card_passes_4_5_to_1(self):
        css = style(page.render([], TAKEN))
        self.assertIn(".num{margin-left:auto;padding-left:8px;color:#a6adc8;", css)
        self.assertIn(".meta{margin-top:4px;display:flex;flex-wrap:wrap;gap:0 10px;color:#a6adc8;", css)

    def test_each_card_carries_its_newest_first_and_recently_updated_rank_in_its_column(self):
        items = [item("issue", 1, "ask", createdAt="2026-10-01T00:00:00Z", updatedAt="2026-11-10T00:00:00Z"),
                 item("issue", 2, "ask", createdAt="2026-11-01T00:00:00Z", updatedAt="2026-11-02T00:00:00Z"),
                 item("issue", 3, "ask", createdAt="2026-10-15T00:00:00Z", updatedAt=None),
                 item("issue", 4, "ask", createdAt=None, updatedAt="2026-11-12T00:00:00Z"),
                 item("PR", 5, "front", createdAt="2026-09-01T00:00:00Z", updatedAt="2026-09-02T00:00:00Z")]
        text = page.render(items, TAKEN)
        got = {int(n): (int(a), int(b)) for a, b, n in re.findall(r'<li class="card" style="--new:(\d+);--upd:(\d+)"><div class="tags">.*?<span class="num">#(\d+)</span>', text)}
        self.assertEqual(got, {1: (2, 1), 2: (0, 2), 3: (1, 3), 4: (3, 0), 5: (0, 0)})
        self.assertEqual(numbers(columns(text)[3]), [1, 3, 2, 4])

    def test_a_title_with_a_tag_and_quotes_comes_out_escaped(self):
        nasty = '<script>alert("x")</script> & \'q\' <img src=x onerror=alert(1)>'
        text = page.render([item(title=nasty, why=nasty, kind="issue<b>", number="1<i>", url='https://github.com/x" onmouseover="y', ci=nasty)] +
                           [item("PR", 2, "front", ci=nasty, title=nasty, url='https://github.com/x" onmouseover="y')], TAKEN)
        self.assertNotIn("<script", text)
        self.assertNotIn("<img", text)
        self.assertNotIn("<b>", text)
        self.assertNotIn("<i>", text)
        self.assertNotIn('" onmouseover', text)
        self.assertIn("&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; &#x27;q&#x27; &lt;img src=x onerror=alert(1)&gt;", text)

    def test_the_page_has_no_script_and_no_link_but_to_github(self):
        items = every_pair() + [item(url="http://example.com/a"), item(url="javascript:alert(1)"), item(url="https://evil.example/https://github.com/")]
        text = page.render(items, TAKEN)
        self.assertNotIn("<script", text.lower())
        links = re.findall(r"https?://[^\s\"'<>]*", text)
        self.assertTrue(links)
        for link in links:
            self.assertTrue(link.startswith("https://github.com/"), link)
        self.assertNotIn("javascript:", text)
        hrefs = re.findall(r'href="([^"]*)"', text)
        self.assertEqual(hrefs.count("https://github.com/morluto/rea"), 1)
        for href in hrefs:
            self.assertTrue(href.startswith("https://github.com/"), href)

    def test_an_item_with_an_unsafe_url_shows_its_title_as_plain_text(self):
        text = page.render([item(number=7, title="plain one", url="javascript:alert(1)"), item(number=8, title="no url", url=None)], TAKEN)
        self.assertIn('<p class="title">plain one</p>', text)
        self.assertIn('<p class="title">no url</p>', text)
        self.assertIn('<span class="num">#7</span>', text)

    def test_it_is_one_file_with_nothing_external(self):
        text = page.render(every_pair(), TAKEN)
        for word in ("<link", "<img", "<iframe", "<script", "src=", "@import", "url(", "@font-face", "<object", "<embed"):
            self.assertNotIn(word, text.lower(), word)
        self.assertIn('<html lang="en">', text)
        self.assertIn('<meta name="viewport" content="width=device-width, initial-scale=1">', text)
        self.assertIn('"Fira Sans",sans-serif', text)
        self.assertIn('"FiraCode Nerd Font Mono",monospace', text)

    def test_every_hex_colour_is_in_the_design_system(self):
        text = page.render(every_pair() + [item(number=2734)], TAKEN)
        text = re.sub(r'<span class="num">#\d+</span>', "", text)
        found = {c.lower() for c in re.findall(r"#[0-9a-fA-F]{3,8}\b", text)}
        self.assertTrue(found)
        self.assertLessEqual(found, set(PALETTE))
        self.assertTrue({"#1e1e2e", "#181825", "#313244", "#45475a", "#c6d0f5", "#cba6f7"} <= found)

    def test_every_rgba_tint_is_a_palette_colour(self):
        css = style(page.render([], TAKEN))
        triples = {tuple(int(n) for n in t) for t in re.findall(r"(?:rgba\(|--c:)(\d+),(\d+),(\d+)", css)}
        self.assertTrue(triples)
        self.assertLessEqual(triples, set(PALETTE.values()))
        self.assertEqual(re.findall(r"(?:\brgb\(|hsl|currentcolor)", css.lower()), [])

    def test_the_tint_classes_the_chips_use_are_in_the_css(self):
        css = style(page.render([], TAKEN))
        for tint in set(page.TINT.values()) | {"soft"}:
            self.assertIn(".%s{--c:" % tint, css)

    def test_there_is_no_em_dash_and_the_only_shadow_is_the_low_mauve_hover_glow(self):
        text = page.render(every_pair(), TAKEN)
        css = style(text)
        self.assertNotIn("\u2014", text)
        self.assertNotIn("text-shadow", css)
        glows = re.findall(r"box-shadow:([^;}]*)", css)
        self.assertEqual(glows, ["0 0 16px rgba(203,166,247,.22)"])
        self.assertIn(".card:hover,.card:focus-within{box-shadow", css)
        self.assertIn("border-radius:14px", css)

    def test_the_layout_scrolls_a_column_inside_and_snaps_sideways_on_a_phone(self):
        css = style(page.render([], TAKEN))
        self.assertIn("grid-auto-columns:min(85vw,22rem)", css)
        self.assertIn("scroll-snap-type:x mandatory", css)
        self.assertIn("max-height:70vh;max-height:70dvh", css)
        self.assertIn("overflow-y:auto", css)
        self.assertIn("repeat(5,minmax(0,1fr))", css)
        self.assertIn("overflow-wrap:anywhere", css)

    def test_line_heights_header_loose_cards_tight(self):
        css = style(page.render([], TAKEN))
        self.assertIn(".top{max-width:52rem;line-height:2}", css)
        self.assertIn("line-height:1.45", css)

    def test_motion_is_only_inside_the_reduced_motion_query(self):
        css = style(page.render([], TAKEN))
        rest = re.sub(r"@media \(prefers-reduced-motion:no-preference\)\{.*?\}\}", "", css, flags=re.S)
        self.assertNotEqual(rest, css)
        for word in ("transition", "animation", "scroll-behavior", "@keyframes"):
            self.assertNotIn(word, rest, word)

    def test_the_header_links_rea(self):
        text = page.render([], TAKEN)
        self.assertIn('<a href="https://github.com/morluto/rea">morluto/rea</a>', text)

    def test_a_time_in_another_zone_is_told_in_utc(self):
        self.assertIn("Data from GitHub at 2027-01-01 00:05 UTC.", page.render([], datetime.fromisoformat("2027-01-01T01:05:00+01:00")))
        self.assertIn("Data from GitHub at 2027-03-02 12:00 UTC.", page.render([], datetime(2027, 3, 2, 12, 0, tzinfo=timezone.utc)))


class SaveTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="rea-page-")
        self.addCleanup(shutil.rmtree, self.d, True)

    def test_it_writes_the_file_and_leaves_no_temp_file(self):
        path = os.path.join(self.d, "board.html")
        page.save(path, "one")
        page.save(path, "two")
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "two")
        self.assertEqual(os.listdir(self.d), ["board.html"])

    def test_a_failed_write_leaves_the_old_file_and_no_temp_file(self):
        path = os.path.join(self.d, "board.html")
        page.save(path, "old")
        with self.assertRaises(TypeError):
            page.save(path, None)
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "old")
        self.assertEqual(os.listdir(self.d), ["board.html"])

    def test_a_path_that_is_a_folder_raises_and_leaves_no_temp_file(self):
        path = os.path.join(self.d, "board.html")
        os.mkdir(path)
        with self.assertRaises(OSError):
            page.save(path, "x")
        self.assertEqual(os.listdir(self.d), ["board.html"])


class MainTest(SetUp):
    def setUp(self):
        super().setUp()
        self.d = tempfile.mkdtemp(prefix="rea-page-")
        self.addCleanup(shutil.rmtree, self.d, True)
        self.board = os.path.join(self.d, "board.json")
        self.out = os.path.join(self.d, "board.html")

    def put(self, board, path=None):
        with open(path or self.board, "w", encoding="utf-8") as fh:
            json.dump(board, fh)

    def run_main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            page.main(list(args))
        return out.getvalue()

    def read(self, path=None):
        with open(path or self.out, encoding="utf-8") as fh:
            return fh.read()

    def test_it_reads_the_board_and_writes_the_page(self):
        self.put({"fetchedAt": TAKEN.isoformat(), "items": every_pair()})
        said = self.run_main("--board", self.board, "--out", self.out)
        self.assertRegex(said, r"^board\.html: written, \d+\.\d KB\n$")
        text = self.read()
        self.assertEqual(sum(counts(text)), sum(len(c[2]) for c in page.COLUMNS))
        self.assertIn("Data from GitHub at 2026-11-14 22:56 UTC.", text)

    def test_the_defaults_are_board_json_and_board_html_in_the_data_folder(self):
        data = os.path.join(self.d, "data")
        os.mkdir(data)
        self.e.write_config({"data_dir": data})
        self.put({"fetchedAt": TAKEN.isoformat(), "items": []}, os.path.join(data, "board.json"))
        self.run_main()
        self.assertEqual(sorted(os.listdir(data)), ["board.html", "board.json"])
        self.assertEqual(counts(self.read(os.path.join(data, "board.html"))), [0] * len(page.COLUMNS))

    def test_an_item_that_is_not_an_object_is_skipped(self):
        self.put({"fetchedAt": TAKEN.isoformat(), "items": [item(number=1), "x", None, 3]})
        self.run_main("--board", self.board, "--out", self.out)
        self.assertEqual(sum(counts(self.read())), 1)

    def test_a_board_that_cannot_be_read_stops_with_a_message(self):
        for text in (None, "not json", "[]", '{"fetchedAt": "2026-11-14T00:00:00Z"}', '{"fetchedAt": "2026-11-14T00:00:00Z", "items": {}}',
                     '{"items": []}', '{"fetchedAt": "later", "items": []}'):
            if text is not None:
                with open(self.board, "w", encoding="utf-8") as fh:
                    fh.write(text)
            with self.assertRaises(SystemExit) as cm:
                self.run_main("--board", self.board, "--out", self.out)
            self.assertIn("page: ", str(cm.exception), text)
            self.assertIn(self.board, str(cm.exception), text)
            self.assertFalse(os.path.exists(self.out), text)

    def test_a_page_that_cannot_be_written_stops_with_a_message(self):
        self.put({"fetchedAt": TAKEN.isoformat(), "items": []})
        with self.assertRaises(SystemExit) as cm:
            self.run_main("--board", self.board, "--out", os.path.join(self.d, "missing", "board.html"))
        self.assertIn("page: cannot write", str(cm.exception))

    def test_run_as_a_script_with_the_isolated_flag(self):
        self.put({"fetchedAt": TAKEN.isoformat(), "items": every_pair()})
        r = subprocess.run([sys.executable, "-I", PAGE, "--board", self.board, "--out", self.out], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, env=dict(os.environ))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith("board.html: written, "))
        self.assertEqual(sum(counts(self.read())), sum(len(c[2]) for c in page.COLUMNS))
        h = subprocess.run([sys.executable, "-I", PAGE, "--help"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertEqual(h.returncode, 0)
        self.assertIn("--board", h.stdout)
        self.assertIn("--out", h.stdout)


if __name__ == "__main__":
    unittest.main()
