# Working on rea-board

A board of open pull requests and issues on morluto/rea, sorted by the help each one needs. It pulls every open pull request and issue with `gh`, sorts them, counts them and draws one page. The README says how to use it.

## Layout

All at the repo root, no package.

- `pull.py`: pulls the open pull requests and issues into `board.json` with a `sort` and a `why` on each, writes the page, adds the counts to `stats.tsv`, prints a summary and the counts.
- `sort.py`: sorts one issue by what it needs, first match wins, from the REA word lists and the item's own facts.
- `lanes.py`: the lane keys and labels, the PR lanes, and the counts of a board (issues by their stored `sort`); `--board BOARD.json`, and `--append STATS.tsv` to add a row. It stops on a `stats.tsv` with other columns.
- `page.py`: draws `board.json` as one static HTML page, a kanban board of five columns of cards, `--board FILE` and `--out FILE`; it reads each item's stored `kind` and `sort`, never the network. The columns are the `COLUMNS` table at the top: a title, a line on what to do, the (kind, sort) pairs it holds. A pair in neither table goes to the first column. `LEFT_OUT` lists the pairs that make no card: pull requests waiting on their author, the maintainers' own items and issues a pull request already fixes. `pull.py` calls it after it saves the board.
- `conf.py`: REA's facts as defaults, and the getters. An optional `config.json`, or the file named by `REA_BOARD_CONFIG`, overrides them.
- `config.example.json`: the two machine overrides someone might want, `data_dir` and `mirror`.
- `tests/`: the tests, one file for each of `pull.py`, `sort.py`, `lanes.py`, `page.py` and `conf.py`.
- `docs/board.png`: the README's picture of the page.
- `tests/fakes/`: `gh`, a fake that answers reads from JSON fixtures and refuses writes, and `env.py`, which puts it on `PATH` for a test.
- `CONTRIBUTING.md`, `AI_POLICY.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `PRIVACY.md`, `DISCLAIMER.md`, `ROADMAP.md`, `CHANGELOG.md` and `.github/` (issue forms, pull request template, CI, the Pages build that pulls and publishes the page every 3 hours, Dependabot): the project's meta files.

## Rules

1. Python standard library and the `gh` command line. `git` only for the optional mirror. Run every script with `python3 -I`.
2. No model, ever. Nothing here calls an AI model or needs a GPU.
3. Public GitHub data only, read-only. It never posts, comments, labels or closes anything, and never reads anybody's private files.
4. REA only. It is built for morluto/rea and may say so in code. It is not a general tool.
5. Keep it simple. A stranger should be able to read it in one sitting. Add nothing just to explain something else.
6. Nothing personal in any file: no machine paths, no computer user names, no home-folder paths, no private note names, no email addresses.
7. Tests run offline and pass from a fresh clone with no config file.

## Checking your work

```sh
python3 -I -m unittest discover -s tests -p 'test_*.py'
```

It must pass with no `config.json`.
