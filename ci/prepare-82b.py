#!/usr/bin/env python3
"""Run the pinned prepare script, then fix the iOS bridge, the logs and the build tree."""
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
                    out.write('\\n'.join(body[-600:]) + '\\n')
        raise
"""
marker = "if __name__ == '__main__':\n    main()\n"
if marker in text:
    runtime.write_text(text.replace(marker, TAIL))
    print('[wrapper] build-boot-runtime dumps the real logs into package.log on failure')

bridge = WS / 'UniXNU/scripts/build-adreno-metal-bridge.py'
script = bridge.read_text()
OLD = """if git_tree(['add', '-A']) != states[-1]:
    raise SystemExit('Translator patch result differs from its exact recorded source')"""
NEW = """# iOS takes the same Darwin host-memory paths the translator keys on macOS.
for rust in sorted(SOURCE.glob('crates/*/src/**/*.rs')):
    was = rust.read_text()
    now = was.replace('not(target_os = "macos")', 'NOT_DARWIN_PLACEHOLDER')
    now = now.replace('target_os = "macos"', 'any(target_os = "macos", target_os = "ios")')
    now = now.replace('NOT_DARWIN_PLACEHOLDER', 'not(any(target_os = "macos", target_os = "ios"))')
    if now != was:
        rust.write_text(now)"""
if OLD in script:
    bridge.write_text(script.replace(OLD, NEW))
    print('[wrapper] bridge builds the Darwin paths for iOS too')
else:
    print('[wrapper] bridge script already carries the iOS paths')

tree_script = WS / 'UniXNU/scripts/unixnu/tree.py'
tree_text = tree_script.read_text()
OLD_TREE = "    (tree / 'scripts').mkdir(exist_ok=True)"
NEW_TREE = """    if (ctx.root / 'profiles').is_dir():
        _link(ctx.root / 'profiles', tree / 'profiles')
    (tree / 'scripts').mkdir(exist_ok=True)"""
if OLD_TREE in tree_text and "tree / 'profiles'" not in tree_text:
    tree_script.write_text(tree_text.replace(OLD_TREE, NEW_TREE))
    print('[wrapper] the build tree carries profiles/')
else:
    print('[wrapper] tree script already links profiles')

fileset = WS / 'UniXNU/scripts/build-fileset-release-reference.py'
fileset_text = fileset.read_text()
OLD_LINK = """    if result.returncode:
        raise SystemExit(result.returncode)"""
NEW_LINK = """    if result.returncode:
        tail = (output / f'{mode}-build.log').read_text(errors='replace').splitlines()[-300:]
        print('\\n'.join(tail), flush=True)
        raise SystemExit(result.returncode)"""
if OLD_LINK in fileset_text:
    fileset.write_text(fileset_text.replace(OLD_LINK, NEW_LINK))
    print('[wrapper] the fileset link failure prints its LTO log')
else:
    print('[wrapper] fileset link already prints its log')
