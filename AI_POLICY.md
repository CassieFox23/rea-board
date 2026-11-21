# AI policy

AI tools are welcome in rea-board. The project is built with them: the commits are written by Claude, a model from Anthropic, working for the maintainer. So this policy is not about keeping AI out. It is about the person behind each contribution.

## The rules

- **Say what you used.** Name the tool and what it did, in the pull request or issue. "It drafted the parser, I wrote the tests" is enough. Using AI is fine. Hiding it is not, and a pull request that hides it will be closed.
- **Every contribution has a human owner.** An agent can do the work, but never alone: a named person owns all of it. The owner has read the final diff, can explain the change without asking the tool, and has run the tests in [CONTRIBUTING.md](CONTRIBUTING.md). Whoever opens a pull request is its owner, unless the pull request names another person and that person agrees in it. "The AI wrote it" is not an answer to a review question. This holds for the maintainer too.
- **Only the owner signs.** The owner fills in the "Human owner" part of the pull request template. An agent leaves it for its person.
- **Reports come from real runs.** A bug report or a wrong column report describes something you saw happen. Security reports go through [SECURITY.md](SECURITY.md), checked by a person first.
- **No agent posts on its own.** An issue, pull request or comment that an agent writes goes out under its owner, checked by them first.
- **The board uses no AI.** No model is called by this code, and none will be added.
- **You can give it.** Opening a pull request means you have the right to submit the change under the GPL-3.0, like the rest of the project.

## For AI agents

An agent that works in this repository reads [AGENTS.md](AGENTS.md) first. It lists the layout, the rules every change keeps and the command that checks the work.

## When it goes wrong

A pull request that looks machine-made and unchecked gets a short, friendly note and is closed. Accounts that open them in bulk are blocked.
