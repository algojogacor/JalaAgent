#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# JalaAgent release script — bumps version across the monorepo.
#
# Usage:
#   bash scripts/release.sh patch   # bump day number
#   bash scripts/release.sh minor   # bump month, reset day
#   bash scripts/release.sh major   # bump year, reset month+day
#
# The version format is date-based: YYYY.M.D (e.g. 2026.6.18).
# All workspace pyproject.toml files and hardcoded source strings are updated.
# ---------------------------------------------------------------------------
set -euo pipefail

SEGMENT="${1:-patch}"

# Read current version from root pyproject.toml
CURRENT=$(grep '^version =' pyproject.toml | head -1 | sed 's/version = "\(.*\)"/\1/')
IFS='.' read -ra PARTS <<< "$CURRENT"

MAJOR="${PARTS[0]}"
MINOR="${PARTS[1]:-0}"
PATCH="${PARTS[2]:-0}"

case "$SEGMENT" in
  major) MAJOR=$((MAJOR + 1)); MINOR=1; PATCH=0 ;;
  minor) MINOR=$((MINOR + 1)); PATCH=0 ;;
  patch) PATCH=$((PATCH + 1)) ;;
  *) echo "Usage: $0 {patch|minor|major}"; exit 1 ;;
esac

NEW_VERSION="$MAJOR.$MINOR.$PATCH"
echo "Bumping version: $CURRENT -> $NEW_VERSION ($SEGMENT)"

# 1. Update root pyproject.toml
sed -i "s/^version = \"$CURRENT\"/version = \"$NEW_VERSION\"/" pyproject.toml

# 2. Update all workspace member pyproject.toml files
while IFS= read -r -d '' f; do
  sed -i "s/version = \"$CURRENT\"/version = \"$NEW_VERSION\"/" "$f"
  echo "  $f"
done < <(find packages extensions cli -name "pyproject.toml" -print0)

# 3. Update __init__.py
sed -i "s/__version__ = \"$CURRENT\"/__version__ = \"$NEW_VERSION\"/" cli/src/jala/__init__.py
echo "  cli/src/jala/__init__.py"

# 4. Refresh lock file
echo "Refreshing uv.lock..."
uv sync --all-packages 2>/dev/null || uv lock

echo ""
echo "Done. Version bumped to $NEW_VERSION"
echo "Next: git tag v$NEW_VERSION && git push origin main --tags"
