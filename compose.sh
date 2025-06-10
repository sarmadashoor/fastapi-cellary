#!/usr/bin/env bash
# Runs docker compose with the proper files

set -e

# Optional cleanup hook (safe even if .setup-scripts doesn't exist)
cleanup() {
  rm -rf .setup-scripts
}

# Trap exit signals for cleanup
trap cleanup EXIT INT TERM ERR

# [OPTIONAL] If you need this directory, define where it really is
# cp -r ../../docker-scripts .setup-scripts

# Correct filenames
docker compose \
  -f docker-compose.yml \
  -f docker-compose-dev.yml \
  "$@"
