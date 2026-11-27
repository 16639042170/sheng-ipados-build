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
        tail = (output / f'{mode}-build.log').read_text(errors='replace').splitlines()[-2000:]
        print('\\n'.join(tail), flush=True)
        raise SystemExit(result.returncode)"""
if OLD_LINK in fileset_text:
    fileset_text = fileset_text.replace(OLD_LINK, NEW_LINK)
    print('[wrapper] the fileset link failure prints 2000 lines of its LTO log')
else:
    print('[wrapper] fileset link already prints its log')

# The pinned fileset script only knew ld's old undefined-symbol format and only
# accepted native_*/boot_log_rounds, so the non-LTO summary block
# (`      _kernel_bootstrap in startup.o`) stubbed nothing at all.
STUB_OLD = '    build_log = (output / f\'{mode}-build.log\').read_text()\n    stub_names = sorted(set(re.findall(r\'^\\s+"(_(?:native_[a-z0-9_]+|boot_log_rounds))"\', build_log, re.M)))\n    if stub_names:\n        (output / \'native-stubs.c\').write_text(\'\'.join(f\'long {name[1:]};\\n\' for name in stub_names))   # the linker names carry the leading underscore\n'
STUB_NEW = '    build_log = (output / f\'{mode}-build.log\').read_text()\n    # ld prints undefined symbols in two shapes and this matcher used to know only one:\n    #   old:  "  \\"_native_ram_block_gpu_addon\\", referenced from:"\n    #   new:  "      _kernel_bootstrap in startup.o"   (summary block, non-LTO link)\n    # The old prefix filter also dropped the remaining old-format names\n    # (_native_verified_*, _sheng_boot_watchdog_policy), so only native_* was ever stubbed.\n    found = set()\n    for line in build_log.splitlines():\n        quoted = re.match(r\'^\\s+"(_?[A-Za-z][A-Za-z0-9_]*)"(?:,|\\s*$)\\s*(?:referenced from:)?$\', line)\n        if quoted and \'auth_ptr$\' not in line:\n            found.add(quoted.group(1))\n            continue\n        summary = re.match(r\'^\\s{4,}(_?[A-Za-z][A-Za-z0-9_]*) in \\S+\\.(?:o|cpo|o\\.cpo)$\', line)\n        if summary:\n            found.add(summary.group(1))\n    stub_names = sorted({name.lstrip(\'_\') for name in found if name})\n    if stub_names:\n        print(\'reference undefined symbols:\', stub_names, flush=True)\n        (output / \'native-stubs.c\').write_text(\n            \'\'.join(f\'long {name} __attribute__((weak, used));\\n\' for name in stub_names))\n'
if STUB_OLD in fileset_text:
    fileset_text = fileset_text.replace(STUB_OLD, STUB_NEW, 1)
    print('[wrapper] the reference kernel stubs every undefined symbol in both ld formats')
elif 'reference undefined symbols:' in fileset_text:
    print('[wrapper] reference stub extractor already covers both ld formats')
else:
    print('[wrapper] fileset stub block differs; left it as it is')

# LTO merges the kernel into justlto.o, which references _kernel_bootstrap that the
# arm64e comparison link cannot resolve. Build this private reference without LTO.
board = WS / 'device/board.toml'
board_text = board.read_text()
REF = '"build-fileset-release-reference.py --tree . --lto"'
NO_LTO = '"build-fileset-release-reference.py --tree ."'
if REF in board_text:
    board.write_text(board_text.replace(REF, NO_LTO, 1))
    print('[wrapper] the reference kernel is built without LTO')
else:
    print('[wrapper] board already builds the reference kernel without LTO')
fileset.write_text(fileset_text)

baseline = WS / 'UniXNU/scripts/build-xnu-4k-baseline.sh'
baseline_text = baseline.read_text()
OLD_BASE = 'EXTRA_MAKE_ARGS+=("LD_KERNEL_ARCHIVES=$KERNEL_EXTRA_ARCHIVES")'
NEW_BASE = ('KERNEL_EXTRA_ARCHIVES="$KERNEL_EXTRA_ARCHIVES -Wl,-undefined,dynamic_lookup"\n'
            + OLD_BASE)
if OLD_BASE in baseline_text and 'dynamic_lookup' not in baseline_text:
    baseline.write_text(baseline_text.replace(OLD_BASE, NEW_BASE))
    print('[wrapper] the baseline kernel keeps its unresolved hooks dynamic')
else:
    print('[wrapper] baseline link already allows dynamic hooks')
