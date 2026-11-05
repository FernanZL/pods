#!/bin/sh
# Run the app as whoever owns the bind-mounted /data on the host, so files the
# backend writes (audio, transcripts, index, sqlite) stay owned by you.
set -e
mkdir -p /data
uid="$(stat -c %u /data)"
gid="$(stat -c %g /data)"
if [ "$(id -u)" = "0" ] && [ "$uid" != "0" ]; then
  exec setpriv --reuid="$uid" --regid="$gid" --clear-groups -- "$@"
fi
exec "$@"
