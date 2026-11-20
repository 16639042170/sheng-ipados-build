#!/usr/bin/env python3
"""Run the pinned prepare script, then make the runtime build print its real logs when it fails."""
import os
import pathlib
import urllib.request

BASE = ('https://raw.githubusercontent.com/16639042170/sheng-ipados-build/'
        '0de6ae85108741afc5241f48e01d6934eec8a2e9/ci/prepare-82b.py')
source = urllib.request.urlopen(BASE, timeout=90).read().decode()
exec(compile(source, BASE, 'exec'), {'__name__': '__main__'})

WS = pathlib.Path(os.environ.get('GITHUB_WORKSPACE', '.'))
runtime = WS / 'UniXNU/scripts/build-boot-runtime.py'
text = runtime.read_text()
TAIL = """if __name__ == '__main__':
    try:
        main()
    except BaseException:
        import glob, os, pathlib
        root = pathlib.Path(__file__).resolve().parents[1]
        log = pathlib.Path(os.environ.get('GITHUB_WORKSPACE', str(root.parent))) / 'package.log'
        with log.open('a', errors='replace') as out:
            for pattern in (str(root / 'out/*/*/logs/*.log'),
                            str(root / 'build/adreno-metal-bridge/build-*.log')):
                for path in glob.glob(pattern):
                    out.write('=== dump %s ===\\n' % path)
                    body = pathlib.Path(path).read_text(errors='replace').splitlines()
                    out.write('\\n'.join(body[-500:]) + '\\n')
        raise
"""
marker = "if __name__ == '__main__':\n    main()\n"
if marker not in text:
    raise SystemExit('[wrapper] build-boot-runtime tail changed')
runtime.write_text(text.replace(marker, TAIL))
print('[wrapper] build-boot-runtime dumps the real logs into package.log on failure')
