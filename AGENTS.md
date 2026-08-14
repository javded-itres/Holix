# Agent notes (Helix workspace)

Full development rules (architecture, extensions, security, deploy): **[RULES.md](RULES.md)**.

## «Сделай релиз»

When the user says **сделай релиз** (or `/make-release`), follow
**[`.grok/skills/make-release/SKILL.md`](.grok/skills/make-release/SKILL.md)**:

1. Open a GitHub PR with the changes (next version + CHANGELOG).
2. Watch GitHub Actions until all checks pass; fix and push if needed.
3. Merge the PR into `main`.
4. Tag `vX.Y.Z` (next number after the latest GitHub release) so GHA creates
   the GitHub Release and publishes to PyPI.

## Production / remote policy (Studio and related)

- **Production** installs of Holix Studio stack: **GitHub Actions only**, **branch `main` only** (Helix + holix-studio + holix-license).
- **Never** without explicit user approval in the **current** turn:
  - rsync/scp/patch application files on prod (or test)
  - manual code checkout on VDS outside Actions
  - “quick hotfix” edits on the server
- Do not treat past deploys as blanket permission.
- Local verification only by default (tests; local Studio restart if needed).
