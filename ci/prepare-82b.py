#!/usr/bin/env python3
"""Pre-package fixups for the sheng iPadOS 27 P1 build.

Run after the three upstream checkouts and before scripts/package.sh. Every
step is idempotent and prints what it changed, so repeated runs are cheap and
the transcript lands in package.log (which the packaging step publishes while
it runs).
"""

import os
import pathlib
import re
import sys

WS = pathlib.Path(os.environ.get('GITHUB_WORKSPACE', '.'))


def marker(name):
    print(f'[marker] {name}', flush=True)


def patch_headers():
    """Give new-file hunks in the git-style patches their `new file mode`.

    Without that line git apply strips the /dev/null prefix down to
    `dev/null` and dies with `error: dev/null: No such file or directory`,
    which is what turnip-frame-diagnostics.patch did on this revision. Patches
    in the older unified format (no `diff --git` line) are left untouched.
    """
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
    """Point the package tree at the kernel's QcomGeniSpi submodule.

    The packaging tree is a git archive, so drivers/QcomGeniSpi is absent even
    though TouchProbe includes GeniSpi.h and the build scripts compile GeniSpi.c
    from it.
    """
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


def board_unused():
    """Mark board constants and helpers the iOS variant compiles out.

    These board sources build with -Werror, but several file-scope constants and
    helpers are only read from XNU_TARGET_OS_OSX blocks that an iOS build drops.
    """
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
    read_pages_cfg()
    geni_spi()
    board_unused()
    marker('fixups done')
