#!/usr/bin/env bash
set -euo pipefail
# Reporting and strategy outputs are disjoint; never force-push or resolve
# conflicting data automatically. Retry only a concurrent fast-forward race.
for attempt in 1 2 3; do
  git fetch origin main
  git rebase origin/main
  if git push origin HEAD:main; then exit 0; fi
done
echo "Publication push failed after three attempts." >&2
exit 1
