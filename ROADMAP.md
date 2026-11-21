# Roadmap

This page lists what is done, what may come and what is not coming. Finished work is in [CHANGELOG.md](CHANGELOG.md). No dates are promised. This is a small project.

## Scope

rea-board does one thing: it shows the open pull requests and issues of morluto/rea, sorted by the help each one needs. It stays small enough to read in one sitting.

## Now

- The board on GitHub Pages, rebuilt every 3 hours by a GitHub Action.

## Next

- Nothing yet.

## Later

- Versions of the page in other languages.

## Not planned

These are out of scope. An issue or pull request that adds one will be closed.

- Any AI model, for sorting or for anything else.
- Writing to GitHub: no posts, comments, labels, closes or reviews.
- Claiming, assigning or voting on cards. Do that on GitHub.
- Repositories other than morluto/rea.
- Reading issue or pull request text. The sort reads only titles, labels and checks.
- More columns or lanes. A new rule moves cards between the five columns.
- Per-person views: no "mine", no leaderboards, no stats about people.
- A server, accounts or a database. The page stays one static file.
- Trackers, analytics, outside scripts or fonts on the page.
- Dependencies beyond the Python standard library and `gh`.
- Notifications: no email, chat or push messages.
