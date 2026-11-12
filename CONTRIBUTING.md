# Contributing

Thanks for your interest. This is a small artistic research project; contributions are
welcome but please open an issue first so we can talk about scope.

## Workflow

1. Open an issue describing the problem or idea.
2. Fork, create a branch, keep one intent per pull request.
3. Run the test suite before opening the pull request:

   ```sh
   uv run pytest -q
   ```

4. Read `AGENTS.md` — it lists the invariants and pitfalls of this codebase
   (it is written for coding agents, but applies to humans too).

## Rules

- No personal data in commits: no real interview content, names, recordings or keys.
- Code, comments and commit messages in English.
- Security issues: see [SECURITY.md](SECURITY.md), never a public issue.

## License

By contributing you agree that your contribution is licensed under the repository's license.
