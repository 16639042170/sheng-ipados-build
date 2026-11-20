#!/usr/bin/env python3
"""Run the pinned prepare script, then point its failure dump at the real logs.

The pinned script replaced package.sh's exec with a run-and-dump, but it looks
for the logs under $ROOT/out (device/) while unixnu writes them under
UniXNU/out. It also echoes them to stdout, which the workflow's package.log
does not always keep; appending to $GITHUB_WORKSPACE/package.log is the file the
publish step tails, so the cargo errors survive.
"""
import os
import pathlib
import urllib.request

BASE = ('https://raw.githubusercontent.com/16639042170/sheng-ipados-build/'
        '0de6ae85108741afc5241f48e01d6934eec8a2e9/ci/prepare-82b.py')
source = urllib.request.urlopen(BASE, timeout=90).read().decode()
exec(compile(source, BASE, 'exec'), {'__name__': '__main__'})

WS = pathlib.Path(os.environ.get('GITHUB_WORKSPACE', '.'))
script = WS / 'device/scripts/package.sh'
text = script.read_text()
before = text
text = text.replace(
    '"$ROOT"/out/*/*/logs/*.log "$ROOT"/build/adreno-metal-bridge/build-*.log',
    '"$ROOT"/../UniXNU/out/*/*/logs/*.log "$ROOT"/../UniXNU/build/adreno-metal-bridge/build-*.log')
text = text.replace(
    'echo "=== $(basename "$f") tail ==="',
    'echo "=== $(basename "$f") tail ===" >> "${GITHUB_WORKSPACE:-$ROOT/..}/package.log"')
text = text.replace(
    'tail -n 2000 "$f"',
    'tail -n 2000 "$f" >> "${GITHUB_WORKSPACE:-$ROOT/..}/package.log"')
if text == before:
    print('[wrapper] package.sh dump block unchanged')
else:
    script.write_text(text)
    print('[wrapper] package.sh dumps UniXNU logs into package.log')
