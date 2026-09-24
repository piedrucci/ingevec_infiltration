#!/bin/sh
set -eu

lock_hash="$(sha256sum package-lock.json | cut -d ' ' -f 1)"
installed_hash="$(cat node_modules/.ingevec-package-lock.sha256 2>/dev/null || true)"

if [ "$lock_hash" != "$installed_hash" ]; then
  npm ci --include=optional
  printf '%s\n' "$lock_hash" > node_modules/.ingevec-package-lock.sha256
fi

exec npm run dev -- --host 0.0.0.0
