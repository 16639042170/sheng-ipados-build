import os
import re
import shutil
import subprocess
from pathlib import Path


def reset_submodule():
    submodule = Path('UniXNU/kits/XnuPrelink')
    if submodule.is_dir():
        subprocess.run(['git', '-C', str(submodule), 'reset', '--hard'], check=False)
        print('reset XnuPrelink to pinned source')


def patch_layout(source):
    text = source.read_text()
    old = """        used = self.used('__TEXT')
        self.reserve('__TEXT', self.hole('__PRELINK_TEXT', used))
        room = self.room('__PRELINK_TEXT', self.placements['__TEXT'])
        self.mapped = {'__TEXT': min(self.segment('__TEXT')['size'], room // 0x1000 * 0x1000)}
        if used > self.mapped['__TEXT']:
            raise ValueError(f'No room for {used:#x} bytes in __PRELINK_TEXT: {self.mapped["__TEXT" ]:#x} bytes of whole pages are free')
"""
    if old not in text:
        print('official __TEXT hole block not found', source)
        return False
    text = text.replace(old, '        self.mapped = {}\n', 1)
    end = '        self.size = self.cursor\n'
    if end not in text:
        print('layout end marker not found', source)
        return False
    addition = """        self.cursor = align(max(self.cursor, max(root['va'] + root['size'] - self.cache.base for root in self.roots.values() if root['size'])))
        size = align(self.segment('__TEXT')['size'])
        root = dict(name='__NATIVE_TEXT', va=self.cache.base + self.cursor,
                    size=size, fileoff=self.cursor, filesize=size)
        self.roots['__NATIVE_TEXT'] = root
        self.reserve('__TEXT', root['va'])
        self.mapped = {'__TEXT': size}
        self.cursor = align(self.cursor + size)
"""
    text = text.replace(end, addition + end, 1)
    info_needle = """        info = self.roots['__PRELINK_INFO']
        info['va'] = self.allocate(info['size'])
"""
    info_replacement = """        info = self.roots['__PRELINK_INFO']
        self.cursor = align(max(self.cursor, max(root['va'] + root['size'] - self.cache.base for root in self.roots.values() if root['size'])))
        info['va'] = self.allocate(info['size'])
"""
    if info_needle in text:
        text = text.replace(info_needle, info_replacement, 1)
    root_needle = """        ordered = sorted((s['va'], s['va'] + s['size']) for s in self.roots.values() if s['size'])
        if any(a[1] > b[0] for a, b in zip(ordered, ordered[1:])):
            raise ValueError('Root mappings overlap')
"""
    root_replacement = """        ordered = sorted((s['va'], s['va'] + s['size']) for s in self.roots.values() if s['size'])
        if any(a[1] > b[0] for a, b in zip(ordered, ordered[1:])):
            raise ValueError('Root mappings overlap: ' + repr([(s['name'], hex(s['va']), hex(s['size'])) for s in sorted((s for s in self.roots.values() if s['size']), key=lambda s: s['va'])]))
"""
    if root_needle in text:
        text = text.replace(root_needle, root_replacement, 1)
    source.write_text(text)
    print('patched final native-text layout', source)
    return True


def patch_cli():
    needle = "    modules = prepare(ctx, steps + (['kernel'] if 'prelink' in steps else []))\n"
    hook = needle + """    patch = os.environ.get('UNIXNU_PRELINK_PATCH')
    if patch:
        subprocess.run([sys.executable, patch], cwd=os.environ.get('GITHUB_WORKSPACE', os.getcwd()), check=True)
"""
    patched = False
    for path in Path('UniXNU').rglob('scripts/unixnu/cli.py'):
        text = path.read_text()
        if 'UNIXNU_PRELINK_PATCH' in text:
            print('cli hook already present', path)
            patched = True
            continue
        if 'import subprocess' not in text:
            text = text.replace('import json\n', 'import json\nimport os\nimport subprocess\n', 1)
        if needle not in text:
            print('cli prepare line not found', path)
            continue
        path.write_text(text.replace(needle, hook, 1))
        print('cli hook added', path)
        patched = True
    return patched


def patch_tree():
    needle = """    components.sync_outputs(ctx, modules)
    return tree
"""
    hook = """    components.sync_outputs(ctx, modules)
    patch = Path(os.environ.get('GITHUB_WORKSPACE', str(ctx.root.parent))) / '.github/ci/patch-prelink.py'
    if patch.is_file():
        import subprocess, sys
        subprocess.run([sys.executable, str(patch)], cwd=str(ctx.root.parent), check=True)
    return tree
"""
    patched = False
    for path in Path('UniXNU').rglob('scripts/unixnu/tree.py'):
        text = path.read_text()
        if 'PRELINK_PATCH' in text:
            print('tree hook already present', path)
            patched = True
            continue
        if needle not in text:
            print('tree assemble end not found', path)
            continue
        if 'import os' not in text:
            text = text.replace('import shutil\n', 'import os\nimport shutil\n', 1)
        path.write_text(text.replace(needle, hook, 1))
        print('tree hook added', path)
        patched = True
    return patched


def main():
    reset_submodule()
    source = Path('UniXNU/kits/XnuPrelink/fileset_layout.py')
    if not source.is_file():
        raise SystemExit(f'source file missing: {source}')
    if not patch_layout(source):
        raise SystemExit('used fileset_layout.py was not patched')
    source_text = source.read_text()
    for path in Path('UniXNU/out').rglob('fileset_layout.py'):
        try:
            path.write_text(source_text)
            print('synced layout', path)
        except OSError as error:
            print('sync failed', path, error)
    for cache in list(Path('UniXNU/kits/XnuPrelink').rglob('__pycache__')) + list(Path('UniXNU/out').rglob('__pycache__')):
        shutil.rmtree(cache, ignore_errors=True)
    if not patch_cli():
        raise SystemExit('no cli.py hook added')
    if not patch_tree():
        print('tree hook not present; cli hook will patch after prepare')
    environment = os.environ.get('GITHUB_ENV')
    if environment:
        with open(environment, 'a', encoding='utf-8') as output:
            output.write('UNIXNU_PRELINK_PATCH=' + os.path.join(os.environ.get('GITHUB_WORKSPACE', os.getcwd()), '.github/ci/patch-prelink.py') + '\n')
        print('exported UNIXNU_PRELINK_PATCH')


if __name__ == '__main__':
    main()
