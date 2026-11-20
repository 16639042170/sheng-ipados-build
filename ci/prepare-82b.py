#!/usr/bin/env python3
"""Run the pinned prepare script, then rewrite package.sh so failure logs land in package.log."""
import os
import pathlib
import urllib.request

BASE = ('https://raw.githubusercontent.com/16639042170/sheng-ipados-build/'
        '0de6ae85108741afc5241f48e01d6934eec8a2e9/ci/prepare-82b.py')
source = urllib.request.urlopen(BASE, timeout=90).read().decode()
exec(compile(source, BASE, 'exec'), {'__name__': '__main__'})

WS = pathlib.Path(os.environ.get('GITHUB_WORKSPACE', '.'))
UPSTREAM = ('https://raw.githubusercontent.com/UniXNU/UniXNU-sheng/'
            'c8f92b208068eeaa4cd2b0f592671f04ee70076e/scripts/package.sh')
original = urllib.request.urlopen(UPSTREAM, timeout=90).read().decode()
old = 'exec python3 "$ROOT/unixnu" release -D "$DEVICE" "$@"'
if old not in original:
    raise SystemExit('[wrapper] package.sh layout changed')
block = '''set +e
LOG="${GITHUB_WORKSPACE:-$DEVICE/..}/package.log"
python3 "$ROOT/unixnu" release -D "$DEVICE" "$@" >> "$LOG" 2>&1
rc=$?
if [ "$rc" -ne 0 ]; then
  for f in "$ROOT"/out/*/*/logs/*.log "$ROOT"/build/adreno-metal-bridge/build-*.log; do
    [ -f "$f" ] || continue
    { echo "=== dump $f ==="; tail -n 400 "$f"; } >> "$LOG"
  done
fi
exit "$rc"'''
text = original.replace(old, block)
(WS / 'device/scripts/package.sh').write_text(text)
print('[wrapper] package.sh dumps the real logs into package.log')
