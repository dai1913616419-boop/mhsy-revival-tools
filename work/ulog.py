"""从 logcat 文本中提取 Unity 标签日志（处理 \r\n）"""
import re, sys

fn = sys.argv[1] if len(sys.argv) > 1 else 'logs_q2.txt'
want_pid = sys.argv[2] if len(sys.argv) > 2 else None
since = sys.argv[3] if len(sys.argv) > 3 else None

pat = re.compile(r'(\d\d-\d\d \d\d:\d\d:\d\d\.\d+)\s+\S/Unity\s+\(\s*(\d+)\)\s*:\s*(.*)')
NOISE = ('ProcessReceive', 'StartReceive', 'received one message')

n = 0
for raw in open(fn, 'rb').read().split(b'\n'):
    l = raw.decode('utf-8', 'replace').rstrip('\r')
    m = pat.search(l)
    if not m:
        continue
    n += 1
    ts, pid, msg = m.group(1), m.group(2), m.group(3).strip()
    if not msg or msg.startswith('(Filename'):
        continue
    if msg in NOISE:
        continue
    if want_pid and pid != want_pid:
        continue
    if since and ts < since:
        continue
    print(ts, '|', pid, '|', msg)
print('--- 共 %d 行 Unity 日志' % n, file=sys.stderr)
