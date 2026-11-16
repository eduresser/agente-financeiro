#!/bin/sh
set -e

DATA_DIR="${DATA_DIR:-/app/data}"
mkdir -p "$DATA_DIR"

if [ "$(id -u)" = "0" ] && [ -n "$HOST_UID" ] && [ "$HOST_UID" != "0" ]; then
  chown -R "$HOST_UID:${HOST_GID:-$HOST_UID}" "$DATA_DIR"
  exec setpriv --reuid="$HOST_UID" --regid="${HOST_GID:-$HOST_UID}" --clear-groups "$@"
fi

exec "$@"
