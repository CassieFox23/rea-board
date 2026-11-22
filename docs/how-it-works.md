# How the code works

This page explains the Python code of rea-board in five levels. Each level adds detail to the level before it. Read as far as you need.

To run the board, see the [README](../README.md).

## Level 1: What it does

REA has many open pull requests and issues. rea-board reads all of them from GitHub. It reads facts like the title, the labels, the checks and the dates. It never reads the text of an issue or a pull request.

A script puts each item in one of five columns, by the help it needs: review or test, fix a bug, ideas and questions, maybe already fixed, or not sorted yet. Then it draws one web page of those columns.

The board only reads. It never writes anything to GitHub. A GitHub Action is scheduled to run it every 3 hours.

## Level 2: One run, step by step

There are five Python files, and each has one job. They pass one file, `board.json`, from step to step.

| File | Job |
|---|---|
| `pull.py` | runs the steps below, in order |
| `sort.py` | gives each issue its group |
| `lanes.py` | gives each PR its group, and counts the groups |
| `page.py` | draws `board.json` as `board.html` |
| `conf.py` | holds REA's facts, like the names of the maintainers |

A run of `pull.py` does this:

1. It asks GitHub for every open pull request (PR), then for every open issue. It uses the `gh` command line tool.
2. If there is a local copy of REA's history (the mirror), it reads the commit messages on REA's main branch from the last 90 days. It looks for numbers like `#123`, to find the items that a commit mentions.
3. It gives every item a `sort` (its group) and a `why` (a short reason). The why is printed on the card.
4. It saves `board.json`. The board from the run before is kept as `board.prev.json`.
5. It draws `board.html`, prints the counts and adds one row to `stats.tsv`.

The sort checks its rules in a fixed order. The first rule that matches decides the group. The rules after it are not checked.

Some groups get no card on the page:

- PRs that wait for their author: drafts, PRs with merge conflicts, and PRs whose checks fail, are still running or did not run. This is true however old the last commit is.
- PRs by the maintainers or by a bot
- issues that are part of the maintainers' plan
- issues that an open PR already fixes

This is why the page shows fewer items than are open.

## Level 3: Each file

### What is in board.json

`board.json` holds the time of the pull (`fetchedAt`), `firstRun`, the GraphQL cost (`graphqlCost`, `graphqlRemaining`) and the list of `items`. This is one issue from `items`. The values are made up:

```json
{"kind": "issue", "number": 512,
 "title": "Crash when opening an APK",
 "author": "someone", "association": "NONE",
 "labels": [],
 "url": "https://github.com/morluto/rea/issues/512",
 "createdAt": "2026-11-01T10:00:00Z",
 "updatedAt": "2026-11-02T10:00:00Z",
 "namedInMain": [], "new": false,
 "sort": "bug",
 "why": "title contains the word \"crash\""}
```

A PR also has `isDraft`, `mergeable`, `ci`, `pushedAt`, `closes`, `additions`, `deletions` and `changedFiles`.

### conf.py

`DEFAULTS` holds REA's facts: `maintainers`, `bot_names`, `plan_authors`, `unsorted_labels` (labels that count for nothing, like `triage`), `data_dir`, `mirror` and `main_since`. `settings()` reads an optional `config.json` and puts its values over the defaults. A `null` value means the default.

Every getter, like `maintainers()` or `mirror()`, calls `settings()` again. A value of the wrong type stops the run with a message. A `repo` key also stops the run, because the repository is always morluto/rea.

### sort.py

`issue_sort()` checks these rules in this order. The first rule that matches gives the group.

1. **inflight**: an open PR says that it closes the issue.
2. **plan**: a maintainer or a plan author opened it, or it has the `roadmap` label, or its title starts with a tag like `[Tracker]`, `[Epic]`, `[Roadmap]` or `[Governance]`.
3. **landed**: a commit on main mentions its number.
4. **ask**: it has a label like `enhancement`, `design`, `documentation` or `question`, or a title tag like `[Feature]` or `[RFC]`. It also matches when the title starts with a verb like "Add" or "Support", or ends with a question mark. This rule is skipped when the issue also has a bug signal: the `bug` label, or a title tag like `[Bug]` or `fix:`.
5. **machine** or **sample**: the title names a system or a tool that not everyone has (macOS, Windows, iOS, IDA Pro, Binary Ninja, a real device), or it asks for a sample file.
6. **bug**: it has a bug signal, or the title has a word like crash, error, fail or hang.
7. **unsorted**: no rule matched.

Some titles and the group they get:

| Title | Group |
|---|---|
| Crash when opening an APK | bug |
| [Feature] add Ghidra 12 support | ask |
| fix: decompiler hangs on Windows | machine |
| Something odd | unsorted |

### lanes.py

`pr_lane()` gives each PR one of six groups. It checks in this order:

1. **flow**: a maintainer or a bot opened it.
2. **landed**: a commit on main mentions its number.
3. If it is a draft, has a merge conflict or its checks failed: **dead** when its newest commit is 14 days old or more, otherwise **author**.
4. **author**: its checks have not passed. They are still running, or none ran.
5. **front**: its checks passed, and it was opened less than 3 days ago.
6. **decide**: its checks passed, and it was opened 3 days ago or more.

`count()` counts the items in each group. `report()` makes the lines that are printed. `append_row()` adds a row to `stats.tsv`.

### page.py

`COLUMNS` is the table of the five columns. Each column has a title, a line that says what to do, and the `(kind, sort)` pairs that it holds. `LEFT_OUT` lists the pairs that get no card. An item whose pair is in neither table goes to the first column.

| Column | Groups |
|---|---|
| Not sorted yet | issue: unsorted |
| Review or test | PR: front, decide |
| Fix a bug | issue: bug, sample, machine |
| Ideas and questions | issue: ask |
| Maybe already fixed | PR and issue: landed |
| No card | PR: author, dead, flow; issue: plan, inflight |

`group()` puts the items in their columns, `card()` writes the HTML of one card, and `render()` builds the whole page. The page is one file with no JavaScript.

### pull.py

`main()` runs the steps of Level 2:

- `paged()` gets the items from GitHub.
- `norm_pr()` and `norm_issue()` turn GitHub's nested answer into flat records.
- `named_in_main()` reads the mirror.
- `sort_items()` gives each item its sort and why.
- `save_board()` saves `board.json`.
- `page.write()` draws the page, and `lanes.py` counts the groups.

## Level 4: How the parts work

### Talking to GitHub

`gql()` in `pull.py` sends every request.

- It runs `gh api graphql`. The `gh` tool does the login, not the script.
- It refuses to send anything that does not start with `query`. A GraphQL mutation, which would change data, cannot be sent.
- When `gh` fails, it tries again after 2, 5, 10 and 20 seconds, so five tries in all. It stops at once on errors that another try cannot fix: a 401 or 404 answer, bad credentials, or `gh` not logged in. The `FINAL` pattern finds these errors.
- It adds up the rate-limit cost of each call. The total is printed at the end and saved in `board.json`.
- `paged()` asks for 50 items per request, and uses the cursor to ask for the next page.
- `read_all()` prints a warning when a PR has more than 20 labels or more than 10 closing links, because the query only asks for that many.

### Merge state

GitHub does not always know at once whether a PR can be merged, so the first answer can be `UNKNOWN`. `settle_mergeable()` waits 5, 10 and then 20 seconds. Each time, it asks again only for the PRs that are still `UNKNOWN`. It asks for up to 50 PRs in one request, with one GraphQL alias for each PR:

```graphql
p512: pullRequest(number: 512) { number mergeable }
```

### Reading the mirror

`named_in_main()` fetches main into the local bare clone, then runs:

```sh
git log refs/heads/main --since=DATE --format=%H%x1f%B%x1e
```

`%x1f` and `%x1e` are the ASCII unit separator and record separator. The first one splits the commit hash from the message. The second one splits one commit from the next.

The pattern `(?<![\w/])#(\d+)\b` finds the number in "fixes #12" or "(#7)". It does not find one in "other/repo#5" or "abc#9".

### Saving files safely

`save_board()` and `replace_atomic()` in `pull.py`, and `save()` in `page.py`, first write a temporary file in the same folder. Then `os.replace()` renames it over the real file. On one file system, a rename is either complete or not done at all, so no program reads a file that is half written. If anything fails, even Ctrl-C, the temporary file is deleted and the error is raised again.

### Rule order, with examples

- "Add support for Hopper on macOS" is **ask**. The ask rule comes before the machine rule.
- "fix: decompiler hangs on Windows" is **machine**. `fix:` is a bug signal, so the ask rule is skipped, and the machine rule comes before the bug rule.
- "Why does rizin need a sample binary?" with the `bug` label is **sample**, for the same reason.

### Reading titles

`LEAD` in `sort.py` matches the start of a title: any `[Tag]` blocks, then a prefix like `fix:` or `feat(ui)!:`. `tag_words()` turns that part into lower-case words. For example, `[Bug][macOS] feat(ui)!: thing` gives `bug`, `macos`, `feat` and `ui`.

Each word list becomes one regular expression. The bug words match the start of a word, so "error" also finds "errored", and "freez" finds "freezes".

### The page

- `e()` escapes every value before it goes into the HTML, because anyone can write a title.
- A title is a link only when its URL starts with `https://github.com/`. Any other URL, like a `javascript:` link, gives a title with no link.
- The three sort buttons are radio buttons, with no JavaScript. Each card holds two numbers as CSS variables, `--new` and `--upd`: its place in the column when sorted newest first, and when sorted by the last update. `ranks()` works out these numbers. A CSS rule like `body:has(#s-new:checked) .card{order:var(--new)}` then changes the order of the cards. "Oldest first" is the order of the HTML itself.
- On a narrow screen, the columns scroll sideways. From 72rem wide, the five columns are side by side.

### Why the scripts change sys.path

Each file except `conf.py` imports another file of the project. The README says to run the scripts with `python3 -I`. In isolated mode (`-I`), Python does not put the script's own folder on the import path. So each of these files adds its own folder with `sys.path.insert(0, ...)` before it imports `conf`, `lanes`, `page` or `sort`.

### Tests

The tests use `unittest` and run offline. `tests/fakes/gh` is a fake `gh` command. `FakeEnv` in `tests/fakes/env.py` puts it first on `PATH` during a test. The fake answers from JSON fixtures, writes every call to a log, and refuses writes with exit code 3.

## Level 5: Rules and side effects

### What the code always keeps true

- **Read only.** `gql()` refuses anything but a query. The fake `gh` in the tests refuses writes, so a write also fails in the tests.
- **Standard library only, no AI model, morluto/rea only.** `REPO` is fixed, and a `repo` key in the config stops the run.
- **The page depends only on `board.json`.** `page.py` reads the stored `kind` and `sort`, and does not use the network. So `page.py --board` draws an old board the same way again.
- **`stats.tsv` only gets new rows,** one for each `fetchedAt`. If its header does not match the current columns, the run stops, so two sets of columns are never mixed.
- **One time for the whole run.** `pull.py` reads the clock once. It uses that time for the sort, the ages on the cards and the counts. When `lanes.py` runs by itself, it uses `fetchedAt`, which is the same time. So it counts the same PR groups that `pull.py` stored.

### What follows from the rules

This is how the code behaves today. To ask for a change, open an issue.

- **An issue can have no card at all.** `closed_by` is built from every open PR, whatever its group. Say an issue's only fix is a PR with failed checks and no new commit for a month. The issue is inflight and the PR is dead, and both get no card.
- **The 14 days only count for stuck PRs:** drafts, merge conflicts and failed checks. A PR whose checks pass stays in Review or test, however old its last commit is.
- **A PR with no checks, or with checks still running,** waits for its author and gets no card.
- **An `UNKNOWN` merge state counts as no conflict.** Only `CONFLICTING` counts. A PR with passing checks that is still `UNKNOWN` after the three waits shows in Review or test, with no "merge conflict" label. The run prints how many PRs stayed `UNKNOWN`.
- **`pushedAt` is not the time of the push.** It is the commit date of the newest commit in the PR. A rebase changes it, but a push of an old commit does not. So "14 days" means that the newest commit is 14 days old or more.
- **front and decide share a column.** The why line on each card says which one it is, and the counts keep them apart.
- **`new` is saved but not shown.** `pull.py` saves it in `board.json` and counts it in its summary. `page.py` does not use it.
- **An unknown config key gives no message.** A misspelled key, like `maintaners`, leaves the default in place. A wrong type stops the run, but an unknown key does not.
- **The config file is read again each time a getter is called.** Importing `pull.py` also reads it, because `pull.py` sets `REPO = conf.repo()` when it loads. The tests import `pull.py` inside `FakeEnv`.
- **The order of the rules decides the result.** When two rules match, the first one wins. So moving one check in `issue_sort()` changes which rule wins.
- **Only the title and the labels decide an issue's group.** The text of an issue is never read. An issue with a vague title and no labels, like "Something odd", goes to Not sorted yet, however clear its text is.
- **"Maybe already fixed" looks back 90 days.** That is `main_since`. The Pages build clones REA with `--shallow-since` set to 90 days ago, to match. A commit older than that is not found.
- **The code that writes a temporary file and renames it is in three places:** `replace_atomic()`, `save_board()` and `page.save()`. Importing it from `pull.py` into `page.py` would make an import loop, because `pull.py` imports `page`.
