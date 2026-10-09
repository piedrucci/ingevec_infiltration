#!/bin/sh
set -eu

lock_hash="$(sha256sum package.json pnpm-lock.yaml | sha256sum | cut -d ' ' -f 1)"
installed_hash="$(cat node_modules/.ingevec-pnpm-lock.sha256 2>/dev/null || true)"

if [ "$lock_hash" != "$installed_hash" ]; then
  pnpm install --frozen-lockfile
  printf '%s\n' "$lock_hash" > node_modules/.ingevec-pnpm-lock.sha256
fi

exec pnpm dev -- --host 0.0.0.0
