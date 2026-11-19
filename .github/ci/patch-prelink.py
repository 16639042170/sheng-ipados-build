import re
from pathlib import Path

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
    if "self.cursor = align(max(self.cursor, self.end('__TEXT_EXEC') - self.cache.base))" in text:
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
