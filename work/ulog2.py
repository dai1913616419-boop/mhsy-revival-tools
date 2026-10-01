"""更健壮的 Unity logcat 提取器。
用法: ulog2.py <logfile> [起始时间]
支持两种格式:
  I/Unity( 1234): msg
  I Unity   : msg   （带 pid/tid 列）
"""
import re, sys

fn = sys.argv[1]
since = sys.argv[2] if len(sys.argv) > 2 else None

pat_a = re.compile(r'(\d\d-\d\d \d\d:\d\d:\d\d\.\d+)\s+\S+/Unity\s*\(\s*(\d+)\)\s*:\s?(.*)')
pat_b = re.compile(r'(\d\d-\d\d \d\d:\d\d:\d\d\.\d+)\s+(\d+)\s+(\d+)\s+\w+\s+Unity\s*:\s?(.*)')

NOISE = ('ProcessReceive', 'StartReceive', 'received one message', '')

out = []
for raw in open(fn, 'rb').read().split(b'\n'):
    l = raw.decode('utf-8', 'replace').rstrip('\r')
    m = pat_b.search(l)
    if m:
        ts, pid, tid, msg = m.group(1), m.group(2), m.group(3), m.group(4)
    else:
        m = pat_a.search(l)
        if not m:
            continue
        ts, pid, msg = m.group(1), m.group(2), '-'
        tid = '-'
    msg = msg.strip()
    if msg in NOISE:
        continue
    if msg.startswith('(Filename:'):
        continue
    if since and ts < since:
        continue
    out.append((ts, pid, msg))

for ts, pid, msg in out:
    print(ts, '|', msg)
print('--- %d lines ---' % len(out), file=sys.stderr)
