#!/usr/bin/env bash
# Configure GitHub deployment environments for PyPI Trusted Publishing.
#
# Prerequisites:
#   - GitHub CLI: gh auth login   (or export GITHUB_TOKEN with repo scope)
#   - PyPI account (manual step in browser — see printed instructions)
#
# Usage:
#   ./scripts/setup_pypi_publish.sh
#   ./scripts/setup_pypi_publish.sh --check   # verify only

set -euo pipefail

OWNER="javded-itres"
REPO="Holix"
PACKAGE="Holix"
WORKFLOW="publish-pypi.yml"
CHECK_ONLY=false

for arg in "$@"; do
  case "$arg" in
    --check) CHECK_ONLY=true ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
  esac
done

header() { echo ""; echo "=== $1 ==="; }

api() {
  local method="$1" path="$2"
  shift 2
  if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    gh api -X "$method" "$path" "$@"
  elif [[ -n "${GITHUB_TOKEN:-}" ]]; then
    curl -fsSL -X "$method" \
      -H "Authorization: Bearer ${GITHUB_TOKEN}" \
      -H "Accept: application/vnd.github+json" \
      -H "X-GitHub-Api-Version: 2022-11-28" \
      "https://api.github.com${path}" "$@"
  else
    echo "ERROR: Not authenticated. Run: gh auth login" >&2
    echo "       or: export GITHUB_TOKEN=<pat with repo scope>" >&2
    exit 1
  fi
}

ensure_environment() {
  local name="$1"
  echo -n "  environment '${name}' ... "
  # null = any branch/tag may deploy (needed for v* tag releases)
  local payload='{"deployment_branch_policy":null}'
  if api PUT "/repos/${OWNER}/${REPO}/environments/${name}" \
      --input - <<<"$payload" >/dev/null; then
    echo "OK"
  else
    echo "FAILED"
    return 1
  fi
}

check_environment() {
  local name="$1"
  if api GET "/repos/${OWNER}/${REPO}/environments/${name}" >/dev/null 2>&1; then
    echo "  [ok] GitHub environment: ${name}"
    return 0
  fi
  echo "  [missing] GitHub environment: ${name}"
  return 1
}

header "Holix PyPI publish setup"
echo "Repository: ${OWNER}/${REPO}"
echo "Package:    ${PACKAGE}"
echo "Workflow:   .github/workflows/${WORKFLOW}"

if $CHECK_ONLY; then
  header "Checking GitHub environments"
  ok=true
  check_environment pypi || ok=false
  check_environment testpypi || ok=false
  header "PyPI (manual)"
  echo "  Open: https://pypi.org/manage/account/publishing/"
  echo "  Pending publisher required (project does not exist on PyPI yet):"
  echo "    PyPI project name: ${PACKAGE}"
  echo "    Owner:             ${OWNER}"
  echo "    Repository:        ${REPO}"
  echo "    Workflow:          ${WORKFLOW}"
  echo "    Environment:       pypi"
  $ok && echo "" && echo "GitHub environments ready." || exit 1
  exit 0
fi

header "Creating GitHub environments"
ensure_environment pypi
ensure_environment testpypi

header "GitHub — done"
echo "Environments created:"
echo "  https://github.com/${OWNER}/${REPO}/settings/environments"

header "PyPI — manual step (browser)"
cat <<EOF

Because Holix is not on PyPI yet, add a PENDING trusted publisher:

  1. Log in: https://pypi.org
  2. Account menu → Publishing:
       https://pypi.org/manage/account/publishing/
  3. Add a new pending publisher (GitHub Actions):
       PyPI project name:  ${PACKAGE}
       Owner:              ${OWNER}
       Repository name:    ${REPO}
       Workflow filename:  ${WORKFLOW}
       Environment name:   pypi
  4. Click Add

(Optional TestPyPI) Repeat on https://test.pypi.org/manage/account/publishing/
  with environment name: testpypi

After both sides are configured, release:

  git tag v0.1.3
  git push origin v0.1.3

Or: GitHub → Actions → Publish to PyPI → Run workflow
     auth: trusted-publishing

Verify setup anytime:

  ./scripts/setup_pypi_publish.sh --check

EOF