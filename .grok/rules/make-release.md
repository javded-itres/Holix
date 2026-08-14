# Trigger: «сделай релиз»

When the user says **сделай релиз**, **сделать релиз**, **make a release**,
or `/make-release`, follow `.grok/skills/make-release/SKILL.md` immediately:

1. Open a GitHub PR with the changes (include next version + CHANGELOG).
2. Watch GitHub Actions until every check is green; fix code and push if not.
3. Merge the PR into `main`.
4. Create the next numbered release: tag `vX.Y.Z` matching `pyproject.toml`
   (GitHub Release + PyPI workflows).

Do not stop after the PR. Do not merge red CI. Do not hotfix production VDS.
