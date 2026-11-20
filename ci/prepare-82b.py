#!/usr/bin/env python3
"""Run the pinned prepare script, then make the unixnu entry dump the real logs on failure."""
import os
import pathlib
import urllib.request

BASE = ('https://raw.githubusercontent.com/16639042170/sheng-ipados-build/'
        '0de6ae85108741afc5241f48e01d6934eec8a2e9/ci/prepare-82b.py')
source = urllib.request.urlopen(BASE, timeout=90).read().decode()
exec(compile(source, BASE, 'exec'), {'__name__': '__main__'})

WS = pathlib.Path(os.environ.get('GITHUB_WORKSPACE', '.'))
entry = WS / 'UniXNU/unixnu'
if not entry.is_file():
    raise SystemExit('[wrapper] unixnu entry missing')
backup = entry.with_suffix('.real')
if not backup.is_file():
    backup.write_text(entry.read_text())
SHIM = '''#!/usr/bin/env python3
import glob
import os
import pathlib
import runpy
import sys

ROOT = pathlib.Path(__file__).resolve().parent
code = 0
sys.argv[0] = str(ROOT / 'unixnu.real')
try:
    runpy.run_path(str(ROOT / 'unixnu.real'), run_name='__main__')
except SystemExit as exc:
    code = exc.code if isinstance(exc.code, int) else 1
    raise
finally:
    if code not in (0, None):
        log = pathlib.Path(os.environ.get('GITHUB_WORKSPACE', str(ROOT.parent))) / 'package.log'
        patterns = (str(ROOT / 'out/*/*/logs/*.log'),
                    str(ROOT / 'build/adreno-metal-bridge/build-*.log'))
        with log.open('a', errors='replace') as out:
            for pattern in patterns:
                for path in glob.glob(pattern):
                    out.write('=== dump %s ===\\n' % path)
                    body = pathlib.Path(path).read_text(errors='replace').splitlines()
                    out.write('\\n'.join(body[-500:]) + '\\n')
'''
entry.write_text(SHIM)
os.chmod(entry, 0o755)
print('[wrapper] unixnu entry dumps out logs and the bridge build log into package.log')
