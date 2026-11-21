# Contributing

Issues and pull requests are welcome. This is a small project kept by one person, so replies can take a while.

## Issues

- **A card in the wrong column**: use the "Wrong column" template. Give the item number, the column it is in, the column it should be in and why.
- **A bug** (an error, a page that does not draw): use the "Bug" template.
- **An idea**: use the "Idea" template, and read [ROADMAP.md](ROADMAP.md) first.
- **A security problem**: do not open an issue. See [SECURITY.md](SECURITY.md).

## Pull requests

Keep them small. Open an issue first for anything bigger than a small fix, so we can agree on it before you spend time on it.

A change is ready when:

- it follows the rules in [AGENTS.md](AGENTS.md): standard library only, no AI model, public GitHub data only, nothing ever posted
- it has a test in `tests/`, and the tests pass
- any AI help is named in the pull request, as [AI_POLICY.md](AI_POLICY.md) asks

To run the tests:

```sh
python3 -I -m unittest discover -s tests -p 'test_*.py'
```

They run offline and need no config file.

By contributing you agree that your work is released under the GPL-3.0, the same as the rest of the project.

Everyone who takes part follows the [Code of Conduct](CODE_OF_CONDUCT.md).
