#!/bin/bash
# Update the v1 tag to point to the latest commit on main
# Usage: ./scripts/update-v1-tag.sh

set -e

BRANCH=$(git branch --show-current)
if [ "$BRANCH" != "main" ]; then
  echo "::error::Must be on main branch. Currently on: $BRANCH"
  exit 1
fi

echo "Fetching latest..."
git pull origin main

echo "Updating v1 tag..."
git tag -f v1
git push -f origin v1

echo "✅ v1 tag updated to latest main"
