"""解析 .NET #US (user string) 堆。

#US 项格式: [压缩长度 total][字符字节 (total-1)][终止字节]
total 的最低位为 flag: 1=UTF-16LE, 0=UTF-8
"""
def parse_us(data):
    strings = {}
    off = 1
    n = len(data)
    while off < n:
        start = off
        b = data[off]
        if b & 0x80 == 0:
            total = b; off += 1
        elif b & 0xC0 == 0x80:
            total = ((b & 0x3F) << 8) | data[off+1]; off += 2
        elif b & 0xE0 == 0xC0:
            total = ((b & 0x1F) << 24) | (data[off+1] << 16) | (data[off+2] << 8) | data[off+3]; off += 4
        else:
            break
        flag = total & 1
        nbytes = total - 1
        if nbytes <= 0:
            strings[start] = ""
            off += total
            continue
        raw = data[off:off+nbytes]
        off += total
        try:
            strings[start] = raw.decode('utf-16-le' if flag else 'utf-8', errors='surrogatepass' if flag else 'replace')
        except Exception:
            strings[start] = repr(raw)
    return strings

class USResolver:
    def __init__(self, pe):
        self.strings = parse_us(pe.net.user_strings.__data__)
    def get(self, off):
        v = self.strings.get(off)
        if v is not None:
            return v
        # 回退: 找最近的前一个入口
        ks = [k for k in self.strings if k <= off]
        return self.strings[max(ks)] + "?" if ks else None
    def dump(self, pat=None):
        import re
        for off in sorted(self.strings):
            s = self.strings[off]
            if pat is None or re.search(pat, s, re.I):
                print(off, "|", s[:200])
