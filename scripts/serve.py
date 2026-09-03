#!/usr/bin/env python3
"""Static dev server with HTTP Range support.

Python's built-in http.server answers every request with the whole file and no
Accept-Ranges header. Chrome will then not report a <video> as seekable on its
first fetch -- seekable stays [0, 0] while buffered fills to the end -- so the
hero sculpture, which is driven by currentTime, sits on frame 0 until the file
is re-served from cache. Real hosting (GitHub Pages, any CDN) supports Range;
this makes the preview behave the same way.

    python3 scripts/serve.py [port]      # .claude/launch.json runs it on 4174
"""
import os, re, sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class _Limited:
    """A file-like that stops after n bytes, so copyfileobj sends one range."""
    def __init__(self, f, n):
        self.f, self.n = f, n
    def read(self, k=-1):
        if self.n <= 0:
            return b''
        k = self.n if k < 0 else min(k, self.n)
        d = self.f.read(k)
        self.n -= len(d)
        return d
    def close(self):
        self.f.close()


class RangeHandler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      '.webm': 'video/webm', '.mp4': 'video/mp4', '.mov': 'video/quicktime'}

    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path) or not os.path.isfile(path):
            return super().send_head()
        size = os.path.getsize(path)
        ctype = self.guess_type(path)
        m = re.match(r'bytes=(\d*)-(\d*)$', self.headers.get('Range') or '')
        if not m:
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(size))
            self.send_header('Accept-Ranges', 'bytes')
            self.end_headers()
            return open(path, 'rb')
        a, b = m.groups()
        start = int(a) if a else max(0, size - int(b))
        end = min(int(b) if (a and b) else size - 1, size - 1)
        if start > end or start >= size:
            self.send_response(416)
            self.send_header('Content-Range', 'bytes */%d' % size)
            self.end_headers()
            return None
        self.send_response(206)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Range', 'bytes %d-%d/%d' % (start, end, size))
        self.send_header('Content-Length', str(end - start + 1))
        self.send_header('Accept-Ranges', 'bytes')
        self.end_headers()
        f = open(path, 'rb')
        f.seek(start)
        return _Limited(f, end - start + 1)

    def log_message(self, *a):  # keep the preview log quiet
        pass


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 4174
    ThreadingHTTPServer(('', port), RangeHandler).serve_forever()
