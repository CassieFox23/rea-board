"""Draw board.json as one static HTML page: a header, three sort buttons, then a kanban board of five columns of cards.

usage: page.py [--board FILE] [--out FILE]

Reads the board and nothing else: no network, and each item's stored kind and sort say its column. Defaults are board.json and
board.html in the data folder (config data_dir). The page is one self-contained file with no script, no font or style file
and no image, and its links go only to github.com. Cards are written oldest first; the sort buttons are plain CSS (radio
buttons, :has() and order), so they need no script. Every value from the board is escaped. To change the columns, edit COLUMNS. The pairs in LEFT_OUT make no
card: pull requests waiting on their author, the maintainers' own items and issues a pull request already fixes. pull.py
writes the page after each pull.
"""
import argparse
import html
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conf  # noqa: E402
import lanes  # noqa: E402

COLUMNS = (
    ("Not sorted yet", "The board could not tell from the title or labels whether each item is a bug, an idea or a question. Open one "
     "on GitHub and comment which it is, so a maintainer can add a label.",
     (("issue", "unsorted"),)),
    ("Review or test", "All CI checks pass and there are no merge conflicts. Read the code change, or test it and comment with the result.",
     (("PR", "front"), ("PR", "decide"))),
    ("Fix a bug", "Bug reports. Reproduce a bug, then fix it. Some need a sample file, a Mac, a Windows PC or a paid tool.",
     (("issue", "bug"), ("issue", "sample"), ("issue", "machine"))),
    ("Ideas and questions", "Feature requests, design proposals and questions. Answer a question, or comment on a request with more detail.",
     (("issue", "ask"),)),
    ("Maybe already fixed", "A commit on main mentions these items. Check whether the commit fixed each one, then comment on the item to say if it is fixed.",
     (("PR", "landed"), ("issue", "landed"))),
)
LEFT_OUT = (("PR", "author"), ("PR", "dead"), ("PR", "flow"), ("issue", "plan"), ("issue", "inflight"))
HOME = {pair: n for n, col in enumerate(COLUMNS) for pair in col[2]}
GITHUB = "https://github.com/"
FAR = datetime.max.replace(tzinfo=timezone.utc)
CI = {"SUCCESS": "CI passing", "FAILURE": "CI failing", "ERROR": "CI failing", "PENDING": "CI running", "EXPECTED": "CI running"}
SAMPLE = "needs a sample file"
MACHINE = "needs a Mac, a Windows PC or a paid tool"
TINT = {"PR": "lavender", "Issue": "teal", "merge conflict": "peach", "CI passing": "green", "CI failing": "red",
        "CI running": "yellow", SAMPLE: "maroon", MACHINE: "rosewater"}
EMPTY = "No items in this column."

CSS = """
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;padding:16px;background:#1e1e2e;color:#c6d0f5;font-family:"Fira Sans",sans-serif;line-height:1.45}
p,h1,h2,ul{margin:0}
a{color:#89b4fa}
a:focus-visible{outline:2px solid #cba6f7;outline-offset:2px}
.mono,.count,.num,.age{font-family:"FiraCode Nerd Font Mono",monospace}
.top{max-width:52rem;line-height:2}
h1{font-size:1.75rem;font-weight:600;line-height:1.3}
.about,.totals{color:#a6adc8}
.totals{display:flex;flex-wrap:wrap;gap:0 16px}
.sorts{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}
.pill{position:relative;display:inline-block;padding:6px 16px;border:1px solid #45475a;border-radius:999px;background:#313244;color:#c6d0f5;cursor:pointer}
.pill input{position:absolute;opacity:0;width:1px;height:1px;margin:0;pointer-events:none}
.pill:has(input:checked){background:#cba6f7;border-color:#cba6f7;color:#1e1e2e}
.pill:has(input:focus-visible){outline:2px solid #cba6f7;outline-offset:2px}
body:has(#s-new:checked) .card{order:var(--new)}
body:has(#s-upd:checked) .card{order:var(--upd)}
.board{display:grid;grid-auto-flow:column;grid-auto-columns:min(85vw,22rem);gap:12px;overflow-x:auto;scroll-snap-type:x mandatory;padding-bottom:12px}
.board,.cards{scrollbar-width:thin;scrollbar-color:#7f849c transparent}
.column{min-width:0;display:flex;flex-direction:column;scroll-snap-align:start;background:#181825;border:1px solid #45475a;border-radius:14px}
.col-head{padding:14px 14px 8px}
.col-title{display:flex;align-items:center;justify-content:space-between;gap:8px}
h2{min-width:0;font-size:1.0625rem;font-weight:600;line-height:1.3;overflow-wrap:anywhere}
.count{flex:none;padding:0 10px;border-radius:999px;background:rgba(203,166,247,.18);color:#c6d0f5;font-size:.8125rem}
.todo{margin-top:4px;color:#a6adc8;font-size:.875rem}
.cards{list-style:none;padding:4px 12px 12px;display:grid;gap:6px;align-content:start;overflow-y:auto;max-height:70vh;max-height:70dvh}
.empty{padding:4px 14px 14px;color:#7f849c}
.card{min-width:0;background:#313244;border:1px solid #45475a;border-radius:14px;padding:10px 12px}
.card:hover,.card:focus-within{box-shadow:0 0 16px rgba(203,166,247,.22)}
.tags{display:flex;flex-wrap:wrap;align-items:center;gap:4px}
.num{margin-left:auto;padding-left:8px;color:#a6adc8;font-size:.8125rem}
.tag{display:inline-flex;align-items:center;gap:6px;padding:0 8px;border-radius:999px;background:rgba(var(--c),.15);color:#c6d0f5;font-size:.75rem}
.tag::before{content:"";width:6px;height:6px;border-radius:50%;background:rgba(var(--c),1)}
.soft{--c:147,153,178}
.lavender{--c:180,190,254}
.teal{--c:148,226,213}
.peach{--c:250,179,135}
.green{--c:166,227,161}
.red{--c:243,139,168}
.yellow{--c:249,226,175}
.maroon{--c:235,160,172}
.rosewater{--c:245,224,220}
.title{margin-top:6px;overflow-wrap:anywhere}
.title a{color:#c6d0f5;text-decoration:none}
.title a:hover{text-decoration:underline}
.meta{margin-top:4px;display:flex;flex-wrap:wrap;gap:0 10px;color:#a6adc8;font-size:.75rem}
.why{color:#a6adc8;overflow-wrap:anywhere}
@media (min-width:72rem){.board{grid-auto-flow:row;grid-auto-columns:auto;grid-template-columns:repeat(5,minmax(0,1fr));overflow-x:visible;scroll-snap-type:none}}
@media (prefers-reduced-motion:no-preference){.card{transition:box-shadow .15s}}
"""


def e(v):
    return html.escape("" if v is None else str(v), quote=True)


def pair(item):
    return str(item.get("kind")), str(item.get("sort"))


def column_of(item):
    """The index in COLUMNS of the column that holds item, or None when its pair is in LEFT_OUT. An item whose
    kind and sort are in neither table goes to the first column."""
    if pair(item) in LEFT_OUT:
        return None
    return HOME.get(pair(item), 0)


def oldest_first(item):
    return lanes.when(item.get("createdAt")) or FAR


def group(items):
    """One list of items for each column in COLUMNS, each list oldest first; an item with no created time goes last."""
    out = [[] for _ in COLUMNS]
    for it in items:
        n = column_of(it)
        if n is not None:
            out[n].append(it)
    return [sorted(got, key=oldest_first) for got in out]


def days(item, taken):
    created = lanes.when(item.get("createdAt"))
    if created is None:
        return ""
    n = max((taken - created).days, 0)
    return "Opened today" if n == 0 else "Opened 1 day ago" if n == 1 else "Opened %d days ago" % n


def chips(item):
    """The words of a card's label chips: its kind; for a PR, draft, merge conflict and its CI state; then what a sort asks for."""
    pr = item.get("kind") == "PR"
    out = ["PR" if pr else "Issue"]
    if pr:
        ci = str(item.get("ci") or "")
        if item.get("isDraft"):
            out.append("draft")
        if item.get("mergeable") == "CONFLICTING":
            out.append("merge conflict")
        out.append(CI.get(ci) or ("CI " + ci.lower() if ci else "no checks ran"))
    if item.get("sort") == "sample":
        out.append(SAMPLE)
    if item.get("sort") == "machine":
        out.append(MACHINE)
    return out


def card(item, taken, new, upd):
    """One card: its chips and number, its title, then its age and why. new and upd are its places in the column when
    sorted newest first and recently updated first, which the sort buttons use through CSS order."""
    url = str(item.get("url") or "")
    title = e(item.get("title") or "(no title)")
    age = days(item, taken)
    meta = ('<span class="age">%s</span>' % e(age) if age else "") + ('<span class="why">%s</span>' % e(item["why"]) if item.get("why") else "")
    out = ['<li class="card" style="--new:%d;--upd:%d">' % (new, upd),
           '<div class="tags">%s<span class="num">#%s</span></div>' % (
               "".join('<span class="tag %s">%s</span>' % (TINT.get(w, "soft"), e(w)) for w in chips(item)), e(item.get("number"))),
           '<p class="title">%s</p>' % ('<a href="%s">%s</a>' % (e(url), title) if url.startswith(GITHUB) else title)]
    if meta:
        out.append('<p class="meta">%s</p>' % meta)
    return "".join(out) + "</li>"


def ranks(items, field):
    """Each item's place when items are sorted by the time in field, newest first; an item with no time goes last."""
    def key(n):
        t = lanes.when(items[n].get(field))
        return (t is None, -t.timestamp() if t else 0)
    return {n: r for r, n in enumerate(sorted(range(len(items)), key=key))}


def column(n, items, taken):
    title, todo, _ = COLUMNS[n]
    new, upd = ranks(items, "createdAt"), ranks(items, "updatedAt")
    cards = ('<ul class="cards">\n%s\n</ul>' % "\n".join(card(it, taken, new[k], upd[k]) for k, it in enumerate(items))
             if items else '<p class="empty">%s</p>' % EMPTY)
    return ('<section class="column"><div class="col-head"><div class="col-title"><h2>%s</h2><span class="count">%d</span></div>\n'
            '<p class="todo">%s</p></div>\n%s\n</section>' % (e(title), len(items), e(todo), cards))


def pulled(taken):
    t = taken.astimezone(timezone.utc)
    return "Data from GitHub at %s UTC." % t.strftime("%Y-%m-%d %H:%M")


SORTS = (
    '<div class="sorts" role="group" aria-label="Sort the cards">\n'
    '<label class="pill"><input type="radio" name="sort" id="s-old" checked>Oldest first</label>\n'
    '<label class="pill"><input type="radio" name="sort" id="s-new">Newest first</label>\n'
    '<label class="pill"><input type="radio" name="sort" id="s-upd">Recently updated</label>\n'
    '</div>')


def render(items, taken):
    """The page as one HTML string: items is a list of board items, taken the aware time they were pulled, which the ages count from."""
    repo = conf.repo()
    groups = group(items)
    head = "\n".join([
        '<header class="top">',
        "<h1>rea-board</h1>",
        '<p class="about">Open pull requests and issues on <a href="%s%s">%s</a>, grouped by the kind of help each one needs.</p>'
        % (GITHUB, e(repo), e(repo)),
        '<p class="totals"><span>%s</span><span>Showing <span class="mono">%s</span> of <span class="mono">%s</span> open pull requests and issues.</span></p>'
        % (e(pulled(taken)), "{:,}".format(sum(len(g) for g in groups)), "{:,}".format(len(items))),
        "</header>\n"])
    body = "\n".join(column(n, got, taken) for n, got in enumerate(groups))
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>rea-board</title>\n<style>'
            + CSS + '</style>\n</head>\n<body>\n' + head + SORTS + '\n<main class="board">\n' + body + '\n</main>\n</body>\n</html>\n')


def save(path, text):
    """Write text to path whole or not at all: a temp file in the same folder, then a rename."""
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=".board-", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write(items, taken, out):
    """Draw the page for items and save it at out; the size in bytes."""
    text = render(items, taken)
    save(out, text)
    return len(text.encode("utf-8"))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Draw board.json as one static HTML page.")
    ap.add_argument("--board", help="the board to read (default: board.json in the data folder)")
    ap.add_argument("--out", help="the page to write (default: board.html in the data folder)")
    a = ap.parse_args(argv)
    board_path = a.board or os.path.join(conf.data_dir(), "board.json")
    out = a.out or os.path.join(conf.data_dir(), "board.html")
    try:
        with open(board_path, encoding="utf-8") as fh:
            board = json.load(fh)
    except (OSError, ValueError) as ex:
        sys.exit("page: cannot read %s (%s)" % (board_path, ex))
    if not isinstance(board, dict) or not isinstance(board.get("items"), list):
        sys.exit("page: %s has no items list" % board_path)
    taken = lanes.when(board.get("fetchedAt"))
    if taken is None:
        sys.exit("page: %s has no fetchedAt that reads as a time" % board_path)
    try:
        size = write([i for i in board["items"] if isinstance(i, dict)], taken, out)
    except OSError as ex:
        sys.exit("page: cannot write %s (%s)" % (out, ex))
    print("%s: written, %.1f KB" % (os.path.basename(out), size / 1024))


if __name__ == "__main__":
    main()
