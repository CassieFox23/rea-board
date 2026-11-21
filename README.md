# rea-board

[![ci](https://github.com/CassieFox23/rea-board/actions/workflows/ci.yml/badge.svg)](https://github.com/CassieFox23/rea-board/actions/workflows/ci.yml)

Open pull requests and issues on morluto/rea, sorted by the help each one needs.

## What it is for

[morluto/rea](https://github.com/morluto/rea) has many open items, and it is hard to see where help is wanted. This board sorts them by script and draws one static page of five columns of cards. It uses no AI model, it reads public data only and it never posts.

![The board: five columns of cards, one per kind of help](docs/board.png)

## Needs

- Python 3.11 or newer
- The [GitHub CLI](https://cli.github.com/) (`gh`), logged in
- Optional: a bare mirror clone of morluto/rea, and `git`, to find items that a commit on main mentions

## Install

Clone this repository. There is nothing to install.

## Use

| Command | What it does |
|---|---|
| `python3 -I pull.py` | pulls every open pull request and issue, sorts them and draws the page |
| `python3 -I page.py --board data/board.json --out data/board.html` | draws the page again from a saved board, with no network |
| `python3 -I lanes.py --board data/board.json` | counts a saved board, with no network |

Run the commands from the repository folder. `-I` makes Python ignore your own Python settings, so the scripts run the same everywhere.

The files go in `data/`: `board.json`, `board.prev.json` (the board before), `board.html` and `stats.tsv`. Open `board.html` in any browser. To move the data folder or to use a mirror, copy `config.example.json` to `config.json` and change it: `data_dir` is the data folder, and `mirror` is the path to a bare clone of morluto/rea. The variable `REA_BOARD_CONFIG` names a different file to use in its place.

## The columns

| Column | What it holds |
|---|---|
| Not sorted yet | Issues that the title and labels do not place |
| Review or test | Pull requests with passing checks and no merge conflicts |
| Fix a bug | Bug reports, including those that need a sample file, a Mac, a Windows PC or a paid tool |
| Ideas and questions | Feature requests, design proposals and questions |
| Maybe already fixed | Items that a commit on main mentions |

Buttons above the board sort the cards in every column: oldest first, newest first or recently updated.

Some groups make no card: pull requests that wait on their author, pull requests with no push for 14 days or more, pull requests that are the maintainers' own work or a bot's, issues that are part of a maintainers' plan and issues that an open pull request already fixes.

## Help

Open a [GitHub issue](https://github.com/CassieFox23/rea-board/issues). For a security problem, read [SECURITY.md](SECURITY.md) and do not open an issue.

A card is a best guess: read [DISCLAIMER.md](DISCLAIMER.md). What the board sends and to whom is in [PRIVACY.md](PRIVACY.md).

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) and [AI_POLICY.md](AI_POLICY.md) first.

## Licence

GPL-3.0. Copyright Cassie_Fox. See [LICENSE](LICENSE).
