import os
import shutil
import subprocess
from pathlib import Path


def patch_layout(source):
    text = source.read_text()
    old = """        used = self.used('__TEXT')
        self.reserve('__TEXT', self.hole('__PRELINK_TEXT', used))
        room = self.room('__PRELINK_TEXT', self.placements['__TEXT'])
        self.mapped = {'__TEXT': min(self.segment('__TEXT')['size'], room // 0x1000 * 0x1000)}
        if used > self.mapped['__TEXT']:
            raise ValueError(f'No room for {used:#x} bytes in __PRELINK_TEXT: {self.mapped["__TEXT"]:#x} bytes of whole pages are free')
"""
    if old not in text:
        return False
    text = text.replace(old, """        self.mapped = {}
        self.placements['__TEXT'] = self.roots['__TEXT']['va']
""", 1)
    end = '        self.size = self.cursor\n'
    if end not in text:
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
    text = text.replace(info_needle, info_replacement, 1)
    source.write_text(text)
    return True


def patch_segmented(source):
    text = source.read_text()
    old = '            source = self.layout.segment(name)\n'
    new = "            source = self.layout.segment('__TEXT') if name == '__NATIVE_TEXT' else self.layout.segment(name)\n"
    if new in text:
        return True
    if old not in text:
        return False
    source.write_text(text.replace(old, new, 1))
    return True


def patch_cli():
    needle = "    modules = prepare(ctx, steps + (['kernel'] if 'prelink' in steps else []))\n"
    hook = needle + """    patch = os.environ.get('UNIXNU_PRELINK_PATCH')
    if patch:
        subprocess.run([sys.executable, patch], cwd=os.environ.get('GITHUB_WORKSPACE', os.getcwd()), check=True)
"""
    for path in Path('UniXNU').rglob('scripts/unixnu/cli.py'):
        text = path.read_text()
        if 'UNIXNU_PRELINK_PATCH' in text:
            return True
        if needle not in text:
            continue
        if 'import subprocess' not in text:
            text = text.replace('import json\n', 'import json\nimport os\nimport subprocess\n', 1)
        path.write_text(text.replace(needle, hook, 1))
        return True
    return False


def main():
    module = Path('UniXNU/kits/XnuPrelink')
    if module.is_dir():
        subprocess.run(['git', '-C', str(module), 'reset', '--hard'], check=False)
    layout = module / 'fileset_layout.py'
    segmented = module / 'fileset_segmented.py'
    if not layout.is_file() or not segmented.is_file():
        raise SystemExit('XnuPrelink sources missing')
    if not patch_layout(layout):
        raise SystemExit('fileset_layout.py patch failed')
    if not patch_segmented(segmented):
        raise SystemExit('fileset_segmented.py patch failed')
    layout_text = layout.read_text()
    segmented_text = segmented.read_text()
    for path in Path('UniXNU/out').rglob('fileset_layout.py'):
        path.write_text(layout_text)
    for path in Path('UniXNU/out').rglob('fileset_segmented.py'):
        path.write_text(segmented_text)
    for cache in list(module.rglob('__pycache__')) + list(Path('UniXNU/out').rglob('__pycache__')):
        shutil.rmtree(cache, ignore_errors=True)
    if not patch_cli():
        raise SystemExit('cli.py hook failed')
    environment = os.environ.get('GITHUB_ENV')
    if environment:
        with open(environment, 'a', encoding='utf-8') as output:
            output.write('UNIXNU_PRELINK_PATCH=' + os.path.join(os.environ.get('GITHUB_WORKSPACE', os.getcwd()), '.github/ci/patch-prelink.py') + '\n')
    print('patched XnuPrelink layout and emitter')


if __name__ == '__main__':
    main()
