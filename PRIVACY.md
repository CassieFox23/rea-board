# Privacy

This page says who learns what when rea-board runs.

| Who | What they get | How |
|---|---|---|
| GitHub | the questions that `pull.py` asks about open pull requests and issues of morluto/rea, sent from your own `gh` login | HTTPS, through `gh` |
| The mirror's remote (GitHub for a clone of morluto/rea) | a `git fetch` of that clone, only if you set a mirror | `git` |

Nobody else is contacted. It reads public data only. It never posts, comments, labels or closes anything.

## What stays on your machine

It writes local files only, in the `data/` folder: `board.json`, `board.prev.json`, `board.html` and `stats.tsv`. They hold public GitHub data and the counts. If you set a mirror in `config.json`, each pull runs `git fetch` on that clone and then reads it locally.

## The hosted page

The board at cassiefox23.github.io is served by GitHub Pages. GitHub learns what any visit to a Pages site tells it. The project adds no counter, cookie or script.

## The page

The page it draws loads nothing from anywhere: no script, no font, no style file and no image. It links only to github.com. When you open a link, GitHub learns what any visit tells it.
