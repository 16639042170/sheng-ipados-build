import os
import re
import subprocess
from pathlib import Path

submodule = Path('UniXNU/kits/XnuPrelink')
if submodule.is_dir():
    subprocess.run(['git', '-C', str(submodule), 'reset', '--hard'], check=False)
    print('reset XnuPrelink to pinned source')

HEAD = r"        self\.mapped = \{'__TEXT': min\(%s, room // 0x1000 \* 0x1000\)\}\n        if used > self\.mapped\['__TEXT'\]:\n"
ROOMS = [
    re.compile(HEAD % r"self\.segment\('__TEXT'\)\['size'\]" + r"(?P<body>.*?)(?=        const = self\.roots\['__DATA_CONST'\])", re.S),
    re.compile(HEAD % r"size" + r"(?P<body>.*?)(?=        const = self\.roots\['__DATA_CONST'\])", re.S),
]
NEW_BODY = '''            size = self.segment('__TEXT')['size']
            self.info = self.roots['__PRELINK_INFO']
            self.cursor = align(max(self.cursor, self.end('__TEXT_EXEC') - self.cache.base))
            self.cursor = align(max(self.cursor, max(root['va'] + root['size'] - self.cache.base for root in self.roots.values() if root['size'])))
            root = dict(name='__NATIVE_TEXT', va=self.cache.base + self.cursor,
                        size=align(size), fileoff=self.cursor, filesize=align(size))
            self.roots['__NATIVE_TEXT'] = root
            self.reserve('__TEXT', root['va'])
            self.cursor = align(self.cursor + size)
            self.mapped = {'__TEXT': size}
'''
INFO_NEEDLE = '''        info = self.roots['__PRELINK_INFO']
        info['va'] = self.allocate(info['size'])
'''
INFO_REPLACEMENT = '''        info = self.info if hasattr(self, 'info') else self.roots['__PRELINK_INFO']
        self.cursor = align(max(self.cursor, max(root['va'] + root['size'] - self.cache.base for root in self.roots.values() if root['size'])))
        info['va'] = self.allocate(info['size'])
        self.roots['__PRELINK_INFO'] = info
'''
ROOT_NEEDLE = """        ordered = sorted((s['va'], s['va'] + s['size']) for s in self.roots.values() if s['size'])
        if any(a[1] > b[0] for a, b in zip(ordered, ordered[1:])):
            raise ValueError('Root mappings overlap')
"""
ROOT_REPLACEMENT = """        ordered = sorted((s['va'], s['va'] + s['size']) for s in self.roots.values() if s['size'])
        if any(a[1] > b[0] for a, b in zip(ordered, ordered[1:])):
            raise ValueError('Root mappings overlap: ' + repr([(s['name'], hex(s['va']), hex(s['size'])) for s in sorted((s for s in self.roots.values() if s['size']), key=lambda s: s['va'])]))
"""

found = False
for path in Path('UniXNU').rglob('fileset_layout.py'):
    text = path.read_text()
    if "self.cursor = align(max(self.cursor, self.end('__TEXT_EXEC') - self.cache.base))" in text and '__NATIVE_TEXT' in text:
        print('already new layout', path)
        found = True
        continue
    replaced = False
    for rooms in ROOMS:
        match = rooms.search(text)
        if not match:
            continue
        text = text[:match.start()] + match.group(0)[:match.start('body')-match.start(0)] + NEW_BODY + text[match.end():]
        replaced = True
        break
    if not replaced:
        print('fallback block not found', path)
        continue
    if INFO_NEEDLE in text:
        text = text.replace(INFO_NEEDLE, INFO_REPLACEMENT, 1)
    if ROOT_NEEDLE in text:
        text = text.replace(ROOT_NEEDLE, ROOT_REPLACEMENT, 1)
    path.write_text(text)
    print('patched new layout', path)
    found = True
if not found:
    raise SystemExit('no fileset_layout.py patched')

CLI_NEEDLE = "    modules = prepare(ctx, steps + (['kernel'] if 'prelink' in steps else []))\n"
CLI_HOOK = CLI_NEEDLE + """    patch = os.environ.get('UNIXNU_PRELINK_PATCH')
    if patch:
        subprocess.run([sys.executable, patch], cwd=os.environ.get('GITHUB_WORKSPACE', os.getcwd()), check=True)
"""
cli_patched = False
for path in Path('UniXNU').rglob('scripts/unixnu/cli.py'):
    text = path.read_text()
    if 'UNIXNU_PRELINK_PATCH' in text:
        print('cli hook already present', path)
        cli_patched = True
        continue
    if 'import subprocess' not in text:
        text = text.replace('import json\n', 'import json\nimport os\nimport subprocess\n', 1)
    if CLI_NEEDLE not in text:
        print('cli prepare line not found', path)
        continue
    text = text.replace(CLI_NEEDLE, CLI_HOOK, 1)
    path.write_text(text)
    print('cli hook added', path)
    cli_patched = True
if not cli_patched:
    raise SystemExit('no cli.py hook added')

TREE_NEEDLE = """    components.sync_outputs(ctx, modules)
    return tree
"""
TREE_HOOK = """    components.sync_outputs(ctx, modules)
    patch = Path(os.environ.get('GITHUB_WORKSPACE', str(ctx.root.parent))) / '.github/ci/patch-prelink.py'
    if patch.is_file():
        import subprocess, sys
        subprocess.run([sys.executable, str(patch)], cwd=str(ctx.root.parent), check=True)
    return tree
"""
tree_patched = False
for path in Path('UniXNU').rglob('scripts/unixnu/tree.py'):
    text = path.read_text()
    if 'PRELINK_PATCH' in text:
        print('tree hook already present', path)
        tree_patched = True
        continue
    if TREE_NEEDLE not in text:
        print('tree assemble end not found', path)
        continue
    if 'import os' not in text:
        text = text.replace('import shutil\n', 'import os\nimport shutil\n', 1)
    text = text.replace(TREE_NEEDLE, TREE_HOOK, 1)
    path.write_text(text)
    print('tree hook added', path)
    tree_patched = True
if not tree_patched:
    print('tree hook not present; cli hook will patch after prepare')

environment = os.environ.get('GITHUB_ENV')
if environment:
    with open(environment, 'a', encoding='utf-8') as output:
        output.write('UNIXNU_PRELINK_PATCH=' + os.path.join(os.environ.get('GITHUB_WORKSPACE', os.getcwd()), '.github/ci/patch-prelink.py') + '\n')
    print('exported UNIXNU_PRELINK_PATCH')
