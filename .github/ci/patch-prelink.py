from pathlib import Path

needle = """        if used > self.mapped['__TEXT']:
            raise ValueError(f'No room for {used:#x} bytes in __PRELINK_TEXT: {self.mapped["__TEXT"]:#x} bytes of whole pages are free')
"""
replacement = """        if used > self.mapped['__TEXT']:
            size = self.segment('__TEXT')['size']
            self.info = self.roots['__PRELINK_INFO']
            self.cursor = align(max(self.cursor, self.end('__TEXT_EXEC') - self.cache.base))
            self.cursor = align(max(self.cursor, max(root['va'] + root['size'] - self.cache.base for root in self.roots.values() if root['size'])))
            root = dict(name='__NATIVE_TEXT', va=self.cache.base + self.cursor,
                        size=align(size), fileoff=self.cursor, filesize=align(size))
            self.roots['__NATIVE_TEXT'] = root
            self.reserve('__TEXT', root['va'])
            self.cursor = align(self.cursor + size)
            self.mapped = {'__TEXT': size}
"""
info_needle = """        info = self.roots['__PRELINK_INFO']
        info['va'] = self.allocate(info['size'])
"""
info_replacement = """        info = self.info if hasattr(self, 'info') else self.roots['__PRELINK_INFO']
        self.cursor = align(max(self.cursor, max(root['va'] + root['size'] - self.cache.base for root in self.roots.values() if root['size'])))
        info['va'] = self.allocate(info['size'])
        self.roots['__PRELINK_INFO'] = info
"""
root_needle = """        ordered = sorted((s['va'], s['va'] + s['size']) for s in self.roots.values() if s['size'])
        if any(a[1] > b[0] for a, b in zip(ordered, ordered[1:])):
            raise ValueError('Root mappings overlap')
"""
root_replacement = """        ordered = sorted((s['va'], s['va'] + s['size']) for s in self.roots.values() if s['size'])
        if any(a[1] > b[0] for a, b in zip(ordered, ordered[1:])):
            raise ValueError('Root mappings overlap: ' + repr([(s['name'], hex(s['va']), hex(s['size'])) for s in sorted((s for s in self.roots.values() if s['size']), key=lambda s: s['va'])]))
"""
pairs = ((needle, replacement), (info_needle, info_replacement), (root_needle, root_replacement))
patched = False
for path in Path('UniXNU').rglob('fileset_layout.py'):
    text = path.read_text()
    if "roots['__NATIVE_TEXT']" in text:
        print('already patched', path)
        patched = True
        continue
    missing = False
    for needle, replacement in pairs:
        if needle not in text:
            print('needle not found', path)
            missing = True
            break
        text = text.replace(needle, replacement, 1)
    if missing:
        continue
    path.write_text(text)
    print('patched', path)
    patched = True
if not patched:
    raise SystemExit('prelink fallback needle not found')
