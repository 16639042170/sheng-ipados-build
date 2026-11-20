#!/usr/bin/env python3
"""Pre-package fixups for the sheng iPadOS 27 P1 build (CPU + GPU sleep).

Run after the three upstream checkouts and before scripts/package.sh. Every
step is idempotent and prints what it changed, so repeated runs are cheap and
the transcript lands in package.log (which the packaging step publishes).
"""

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

WS = pathlib.Path(os.environ.get('GITHUB_WORKSPACE', '.'))


def marker(name):
    print(f'[marker] {name}', flush=True)


def patch_headers():
    """Give new-file hunks in the git-style patches their `new file mode`."""
    marker('patch headers')
    root = WS / 'UniXNU/patches'
    fixed = []
    for patch in sorted(root.rglob('*.patch')):
        text = patch.read_text()
        if '--- /dev/null' not in text:
            continue
        lines = text.splitlines(True)
        out = []
        for index, line in enumerate(lines):
            out.append(line)
            if (line.startswith('diff --git ')
                    and index + 1 < len(lines)
                    and lines[index + 1].startswith('--- /dev/null')):
                out.append('new file mode 100644\n')
                fixed.append(patch.relative_to(WS).as_posix())
        patch.write_text(''.join(out))
    print('new-file headers added:', fixed)
    bad = []
    for patch in sorted(root.rglob('*.patch')):
        lines = patch.read_text().splitlines(True)
        for index, line in enumerate(lines):
            if not line.startswith('--- /dev/null'):
                continue
            window = lines[max(0, index - 3):index]
            if (any(w.startswith('diff --git ') for w in window)
                    and not any(w.startswith('new file mode') for w in window)):
                bad.append(patch.relative_to(WS).as_posix())
    if bad:
        sys.exit('headerless new file in ' + ', '.join(bad))


def metal2vulkan_pin():
    """Pin the translator to the revision the GPU sleep bridge was written against.

    82b847c records metal2vulkan 624bab39, but the bridge patches that come with
    AdrenoMetal 8c7f950 (the GPU-sleep commit) are diffs against 555b13d5: patch
    0004 carries `index a685b0dcb..`, which is that revision's
    crates/metal2vulkan-air/src/canon/mod.rs blob, and the 0040 patch name says so
    too. Applying them on 624bab39 fails at 0004, so move the recorded pin and
    its file hashes together.
    """
    marker('metal2vulkan pin')
    inputs = WS / 'UniXNU/scripts/data/gpu-metal-vulkan-inputs.json'
    if not inputs.is_file():
        sys.exit('gpu-metal-vulkan-inputs.json missing at ' + str(inputs))
    commit = '555b13d57e09bff70996a88cff64f1275256d5cf'
    hashes = {
        'README.md': '7fdda13d0b2bb73779b97186acb6f36dca75506cefe41b03214685d25bb0ae10',
        'Cargo.toml': '878c6ad5ce7efba58955114fe0c7a61a7372c9304b3ea244bc370cf158e5ad13',
        'crates/metal2vulkan/src/device/policy.rs':
            '9672e8d38f1cc497164fc21e4a44148eae10a7acd02f63c6fd746460c9cc2bf6',
    }
    data = json.loads(inputs.read_text())
    translator = data.get('translator', {})
    print('pin before:', translator.get('commit'))
    if translator.get('commit') == commit and translator.get('files') == hashes:
        print('already pinned')
    else:
        translator['commit'] = commit
        translator['files'] = hashes
        data['translator'] = translator
        inputs.write_text(json.dumps(data, indent=2) + '\n')
        print('pin after:', commit)
    # The deps stage may already have fetched the old pin into the reference
    # cache; build-boot-runtime's checkout() refuses a cache whose HEAD differs
    # from the pin instead of fetching the new one, so drop it here.
    cache = WS / 'UniXNU/.cache/gpu-reference/metal2vulkan'
    if cache.is_dir():
        head = subprocess.check_output(['git', '-C', str(cache), 'rev-parse', 'HEAD'],
                                       text=True).strip()
        print('cached metal2vulkan HEAD:', head)
        if head != commit:
            shutil.rmtree(cache)
            print('removed the stale metal2vulkan checkout')


def bridge_patch_list():
    """Make the Metal bridge apply the patch set the AdrenoMetal pin ships.

    The bridge script of 82b847c lists the recorded patches by name (0001..0030).
    The AdrenoMetal revision that carries GPU sleep renumbered them
    (0002/0004/.../0040+), so the recorded names no longer exist and git apply
    aborts before it can build anything. Sorting the directory and applying what
    is there keeps both revisions on their own list.
    """
    marker('bridge patch list')
    script = WS / 'UniXNU/scripts/build-adreno-metal-bridge.py'
    if not script.is_file():
        sys.exit('build-adreno-metal-bridge.py missing at ' + str(script))
    directory = WS / 'UniXNU/drivers/AdrenoMetal/bridge/patches'
    patches = sorted(directory.glob('*.patch'))
    print('bridge patches on disk:', len(patches), [p.name for p in patches[:4]])
    if not patches:
        sys.exit('AdrenoMetal/bridge/patches is empty at ' + str(directory))
    text = script.read_text()
    block = re.compile(r"PATCHES = \[ROOT / 'drivers/AdrenoMetal/bridge/patches' / name for name in \[.*?\]\]", re.S)
    replacement = "PATCHES = sorted((ROOT / 'drivers/AdrenoMetal/bridge/patches').glob('*.patch'))"
    if block.search(text):
        script.write_text(block.sub(replacement, text, count=1))
        print('rewrote PATCHES to the patches on disk')
    else:
        print('PATCHES block not found; left the script as it is')


def read_pages_cfg():
    """Widen metal2vulkan's read_pages cfg to the iOS target."""
    marker('read_pages')
    found = []
    for root, dirs, files in os.walk(WS / 'UniXNU'):
        dirs[:] = [d for d in dirs if d not in ('.git', 'out', 'build', 'target')]
        if 'copied.rs' in files:
            found.append(pathlib.Path(root) / 'copied.rs')
    print('copied.rs candidates:', [str(p) for p in found])
    widened = 0
    for path in found:
        text = path.read_text()
        if 'fn read_pages' not in text:
            continue
        changed = False
        for os_name in ('macos', 'linux'):
            old = '#[cfg(target_os = "%s")]\npub(crate) fn read_pages' % os_name
            new = '#[cfg(any(target_os = "%s", target_os = "ios"))]\npub(crate) fn read_pages' % os_name
            if old in text:
                text = text.replace(old, new)
                changed = True
        if changed:
            path.write_text(text)
            widened += 1
            print('widened', path)
    print('widenings:', widened)


def geni_spi():
    """Point the package tree at the kernel's QcomGeniSpi submodule."""
    marker('geni spi')
    package = WS / 'device/package'
    users = [p.name for p in package.glob('*.cpp')
             if 'GeniSpi.h' in p.read_text(errors='ignore')]
    scripts = [s for s in sorted((WS / 'UniXNU/scripts').glob('build-*.py'))
               if 'drivers/QcomGeniSpi' in s.read_text(errors='ignore')]
    print('GeniSpi.h included by:', users)
    print('build scripts referencing the submodule:', [s.name for s in scripts])
    if not users and not scripts:
        return
    geni = WS / 'UniXNU/drivers/QcomGeniSpi'
    if not geni.is_dir():
        sys.exit('QcomGeniSpi submodule missing at ' + str(geni))
    headers = sorted(geni.glob('*.h'))
    for header in headers:
        (package / header.name).write_bytes(header.read_bytes())
    print('copied headers:', [h.name for h in headers])
    prologue = ("import os\n"
                "from pathlib import Path as _GeniPath\n"
                "QCOM_GENI_SPI = _GeniPath(os.environ['GITHUB_WORKSPACE']) / 'UniXNU/drivers/QcomGeniSpi'\n")
    for script in scripts:
        text = script.read_text()
        body = re.sub(r"ROOT\s*/\s*'drivers/QcomGeniSpi/([^']+)'", r"QCOM_GENI_SPI / '\1'", text)
        body = re.sub(r"ROOT\s*/\s*'drivers/QcomGeniSpi'", 'QCOM_GENI_SPI', body)
        if 'drivers/QcomGeniSpi' in body:
            sys.exit('leftover submodule reference in ' + script.name)
        lines = body.splitlines(True)
        start = 1 if lines and lines[0].startswith('#!') else 0
        lines.insert(start, prologue)
        script.write_text(''.join(lines))
        print('rewrote', script.name)


def conflicting_diagnostics():
    """Drop diagnostic patches whose instrumentation a checkpoint patch already adds.

    `sheng-startup-failure-log.patch` inserts boot_progress_stage() calls next to
    the Data-mount block, but the checkpoint patches in the same series already
    put those lines there, so the hunk no longer applies
    (bsd/kern/kern_exec.c:10118). These two patches are observation only: the
    functional code and the checkpoint logging stay in the tree, only the extra
    boot_log_* hooks are lost.
    """
    marker('diagnostic patches')
    series = WS / 'device/patches/xnu-12377/series'
    if not series.is_file():
        sys.exit('series missing at ' + str(series))
    drop = {'sheng-startup-failure-log.patch', 'sheng-process-exit-log.patch'}
    lines = series.read_text().splitlines(True)
    removed = [line.strip() for line in lines
               if line.strip() and pathlib.PurePosixPath(line.strip()).name in drop]
    kept = [line for line in lines
            if not line.strip() or pathlib.PurePosixPath(line.strip()).name not in drop]
    if removed:
        series.write_text(''.join(kept))
    print('dropped diagnostic patches:', removed)


def package_log_tail():
    """Make a failed release print the runtime log it keeps in logs/.

    package.sh execs unixnu and lets its exit status through; unixnu writes the
    real error to out/.../logs/runtime.log, so package.log only shows the
    failed command. Replacing the exec with a run-and-dump keeps the status and
    puts the tail in the published log.
    """
    marker('package log tail')
    script = WS / 'device/scripts/package.sh'
    if not script.is_file():
        sys.exit('package.sh missing at ' + str(script))
    text = script.read_text()
    exec_line = 'exec python3 "$ROOT/unixnu" release -D "$DEVICE" "$@"\n'
    if exec_line not in text:
        print('exec line not found; left package.sh as it is')
        return
    replacement = (
        'set +e\n'
        'python3 "$ROOT/unixnu" release -D "$DEVICE" "$@"\n'
        'rc=$?\n'
        'set -e\n'
        'if [ "$rc" -ne 0 ]; then\n'
        '  for f in "$ROOT"/out/*/*/logs/*.log; do\n'
        '    [ -f "$f" ] || continue\n'
        '    { echo "=== $(basename "$f")"; tail -n 300 "$f"; } >&2\n'
        '  done\n'
        '  exit "$rc"\n'
        'fi\n'
    )
    script.write_text(text.replace(exec_line, replacement, 1))
    print('package.sh now dumps logs/ on failure')


def board_unused():
    """Mark board constants and helpers the iOS variant compiles out."""
    marker('board unused')
    types = (r'(?:static\s+)?(?:bool|int|void|uint32_t|uint64_t|int32_t|int64_t|'
             r'size_t|IOReturn|const char \*)\s+\w+\s*\(')
    for cpp in sorted((WS / 'device/package').glob('*.cpp')):
        text = cpp.read_text()
        before = text
        text = re.sub(r'^constexpr ', '[[maybe_unused]] constexpr ', text, flags=re.M)
        text = re.sub(r'^(' + types + r')', r'[[maybe_unused]] \1', text, flags=re.M)
        text = re.sub(r'^(static const char \w+\[\])(.*)$', r'\1 __attribute__((unused))\2', text, flags=re.M)
        if text != before:
            cpp.write_text(text)
            print(cpp.name, 'patched')


if __name__ == '__main__':
    patch_headers()
    metal2vulkan_pin()
    bridge_patch_list()
    read_pages_cfg()
    geni_spi()
    conflicting_diagnostics()
    package_log_tail()
    board_unused()
    marker('fixups done')
