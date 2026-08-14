---
name: make-release
description: >
  Ship Holix through GitHub: open a PR, wait until Actions are green (fix
  code if needed), merge to main, then cut the next numbered GitHub release.
  Use when the user says «сделай релиз», «сделать релиз», «make a release»,
  «create release», «cut a release», or runs /make-release.
---

# Holix release («сделай релиз»)

When the user says **сделай релиз** (or equivalent), execute this pipeline
end-to-end. Do not stop after the PR. Do not skip CI. Do not tag before merge.

Canonical package rules: `RULES.md` §8. This skill is the operational loop.

## Preconditions

- Repo: `javded-itres/Holix`. Default branch: `main`.
- Auth: `gh auth status` must be logged in.
- Fetch first: `git fetch origin --tags`.
- Next version = latest GitHub release + **patch** (`1.0.7` → `1.0.8`), unless
  the user asked for minor/major.
- Confirm versions agree before tagging:
  - `pyproject.toml` `[project].version`
  - `cli/__init__.py` `__version__`
  - latest `gh release list` / `git tag`
- Do **not** rsync/scp/hotfix production. Tag on `main` is enough: GHA
  `GitHub Release` + `Publish to PyPI` run from `vX.Y.Z`.
- Run `./scripts/lint.sh` (or `--fix`) before every push.

## 1) PR with the changes

Include **code + version bump + changelog** in the same PR so there is one
merge, then a tag.

1. If an open PR already covers this work, reuse it and add the bump there
   if missing.
2. Otherwise branch from up-to-date `origin/main`:
   `release/X.Y.Z` (example: `release/1.0.8`).
3. Commit the user's uncommitted/unmerged work (no secrets, no
   `node_modules/`, no local `.env`).
4. Bump version with `scripts/versioning.py` (or edit both files):
   - `pyproject.toml`
   - `cli/__init__.py`
5. Update `docs/CHANGELOG.md`:
   - Move `## Unreleased` notes into `## X.Y.Z — YYYY-MM-DD`
   - Leave a fresh empty `## Unreleased`
   - Write Added/Fixed/Tests from the actual diff
6. Push and open PR → `main`:

```bash
gh pr create --base main --title "Holix X.Y.Z" --body "$(cat <<'EOF'
## Summary
Release Holix X.Y.Z.

## Checklist
- [ ] Version matches in pyproject.toml and cli/__init__.py
- [ ] docs/CHANGELOG.md has section X.Y.Z
- [ ] CI green (ruff + pytest matrix)

After merge: tag `vX.Y.Z` (creates GitHub Release + PyPI).
EOF
)"
```

## 2) GitHub tests until green

Watch **GitHub Actions on the PR**, not only local pytest.

```bash
gh pr checks <n> --watch
# or
gh run watch <run-id>
```

On failure:

1. `gh run view <id> --log-failed` (or job logs).
2. Fix the code / tests / ruff.
3. Local: `./scripts/lint.sh` then targeted pytest.
4. Commit, push, re-watch.

Repeat until **every** required check is green. Do not merge red CI.
If a failure needs a product decision, stop and ask — do not paper over it.

## 3) Merge into `main`

User already authorized merge as part of this command.

```bash
gh pr merge <n> --merge --delete-branch
```

Use `--squash` only if the user asked. Wait until the PR is `MERGED`.
Then `git checkout main && git pull origin main`.

Verify `main` now has version `X.Y.Z`.

## 4) Next numbered GitHub release

Tag **must** match `pyproject.toml`. Do not create a GitHub release by hand
if the tag workflow can do it.

```bash
git checkout main
git pull origin main
python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"
git tag vX.Y.Z
git push origin vX.Y.Z
```

Watch:

- `GitHub Release` → https://github.com/javded-itres/Holix/releases/tag/vX.Y.Z
- `Publish to PyPI`

```bash
gh run list --branch vX.Y.Z --limit 5
gh release view vX.Y.Z
```

If the tag workflow fails because CHANGELOG has no `## X.Y.Z` section, fix
on a follow-up PR, delete/re-push the tag only with `--force-with-lease`
after saying so. Prefer a new patch over rewriting a published tag.

## Report back

When done, reply with:

- PR URL and merge SHA
- Version `X.Y.Z` / tag `vX.Y.Z`
- Release URL
- CI + PyPI workflow status
