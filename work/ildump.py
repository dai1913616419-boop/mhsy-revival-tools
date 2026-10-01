"""带完整 token 解析的 IL 反汇编器。
用法: ildump.py <dll> <TypeName> <MethodName> [起始IL偏移] [结束IL偏移]
偏移为十六进制（如 10e1e3），省略则全量打印。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dnfile
from dncil.cil.body import CilMethodBody
from dncil.clr.token import Token, StringToken
from disasm3 import Reader
from usheap import USResolver

TBL = {0: 'Module', 1: 'TypeRef', 2: 'TypeDef', 4: 'Field', 6: 'MethodDef',
       8: 'Param', 9: 'InterfaceImpl', 10: 'MemberRef', 11: 'Constant',
       14: 'DeclSecurity', 17: 'StandAloneSig', 20: 'Event', 23: 'Property',
       24: 'MethodSemantics', 25: 'MethodImpl', 26: 'ModuleRef',
       27: 'TypeSpec', 28: 'ImplMap', 29: 'FieldRVA', 32: 'Assembly',
       35: 'AssemblyRef', 38: 'File', 39: 'ExportedType', 40: 'ManifestResource',
       41: 'NestedClass', 42: 'GenericParam', 43: 'MethodSpec', 44: 'GenericParamConstraint',
       112: 'US'}


class Ill:
    def __init__(self, dll):
        self.pe = dnfile.dnPE(dll)
        self.mdt = self.pe.net.mdtables
        self.TN = {i: ((t.TypeNamespace.value or '') + '.' + t.TypeName.value).lstrip('.')
                   for i, t in enumerate(self.mdt.TypeDef.rows, 1)}
        self.MN = {i: str(m.Name) for i, m in enumerate(self.mdt.MethodDef.rows, 1)}
        self.FN = {i: str(f.Name) for i, f in enumerate(self.mdt.Field.rows, 1)}
        self.TRN = {i: ((tr.TypeNamespace.value or '') + '.' + tr.TypeName.value).lstrip('.')
                    for i, tr in enumerate(self.mdt.TypeRef.rows, 1)}
        self.ARN = {i: str(a.Name) for i, a in enumerate(self.mdt.AssemblyRef.rows, 1)}
        self.us = self.pe.net.user_strings
        self.mr_cache = {}

    def mr(self, rid):
        if rid in self.mr_cache:
            return self.mr_cache[rid]
        m = self.mdt.MemberRef.rows[rid - 1]
        name = str(m.Name)
        owner = '?'
        sig = ''
        cls = m.Class
        try:
            tb = cls.table.name
        except Exception:
            tb = None
        if tb == 'TypeRef':
            r = cls.row
            tn = ((r.TypeNamespace.value or '') + '.' + (r.TypeName.value or '')).lstrip('.')
            sc = r.ResolutionScope
            asm = ''
            try:
                if sc.table is not None and sc.table.name == 'AssemblyRef':
                    asm = ' @' + self.ARN[sc.row_index]
            except Exception:
                pass
            owner = tn + asm
        elif tb == 'TypeSpec':
            owner = '<TypeSpec>'
        else:
            owner = str(tb)
        # Signature
        try:
            s = bytes(m.Signature.value)
            sig = self.decode_mrsig(s)
        except Exception:
            sig = ''
        out = '%s::%s%s' % (owner, name, sig)
        self.mr_cache[rid] = out
        return out

    def decode_mrsig(self, s):
        """粗略解码 memberref 签名 -> (params)"""
        if not s or s[0] != 0x20:
            return ''
        i = 1
        if i >= len(s):
            return ''
        n = s[i]
        i += 1
        args = []
        ELEM = {0x01: 'void', 0x02: 'bool', 0x03: 'char', 0x04: 'sbyte', 0x05: 'byte',
                0x06: 'int16', 0x07: 'uint16', 0x08: 'int32', 0x09: 'uint32',
                0x0a: 'int64', 0x0b: 'uint64', 0x0c: 'float', 0x0d: 'double',
                0x0e: 'string', 0x11: 'V<T>', 0x12: 'class', 0x13: '!T', 0x14: 'arr',
                0x15: 'G<T>', 0x18: 'intptr', 0x19: 'uintptr', 0x1c: 'object',
                0x1d: 'S<T>', 0x1e: 'mvar'}
        for _ in range(n):
            if i >= len(s):
                break
            e = s[i]
            if e in (0x11, 0x12, 0x15, 0x1d):
                i += 1
                # compressed type token
                v, i = self._comp(s, i)
                nm = self.TRN.get(v & 0xffffff, '?') if (v >> 24) in (1, 2) else '?'
                args.append(nm.split('.')[-1])
            elif e == 0x13 or e == 0x1e:
                i += 2
                args.append('!T')
            else:
                args.append(ELEM.get(e, hex(e)))
                i += 1
        return '(' + ', '.join(args) + ')'

    def _comp(self, s, i):
        x = s[i]
        if x & 0x80 == 0:
            return x, i + 1
        if x & 0xC0 == 0x80:
            return ((x & 0x3f) << 8) | s[i + 1], i + 2
        return (x & 0x1f) << 24 | s[i + 1] << 16 | s[i + 2] << 8 | s[i + 3], i + 4

    def describe(self, ins):
        o = ins.operand
        if o is None:
            return ''
        if isinstance(o, StringToken):
            try:
                off = getattr(o, 'offset', None)
                if off is None:
                    off = o.value & 0xffffff
                return '"%s"' % self.us.get(off)
            except Exception:
                return 'str'
        if hasattr(o, 'value'):
            v = o.value
            tb = (v >> 24) & 0xff
            rid = v & 0xffffff
            if tb == 10:
                return self.mr(rid)
            if tb == 4:
                return 'field#' + str(rid) + ' ' + self.FN.get(rid, '?')
            if tb == 6:
                return 'mdef#' + str(rid) + ' ' + self.MN.get(rid, '?')
            if tb == 1:
                return 'typeref#' + str(rid) + ' ' + self.TRN.get(rid, '?')
            if tb == 2:
                return 'typedef#' + str(rid) + ' ' + self.TN.get(rid, '?')
            # branch target
            if ins.opcode.name.startswith('br') or ins.opcode.name in ('leave', 'leave.s'):
                return 'IL_%05x' % o
            return str(o)
        return str(o)

    def find(self, type_name, method_name):
        t = None
        for i, tt in enumerate(self.mdt.TypeDef.rows, 1):
            if ((tt.TypeNamespace.value or '') + '.' + (tt.TypeName.value or '')).lstrip('.') == type_name:
                t = tt
                break
        if t is None:
            raise SystemExit('type not found: ' + type_name)
        for m in t.MethodList:
            if str(m.row.Name) == method_name:
                return t, m.row
        raise SystemExit('method not found: ' + method_name)

    def dump(self, tname, mname, lo=None, hi=None):
        t, m = self.find(tname, mname)
        body = CilMethodBody(Reader(self.pe, m.Rva))
        ins = list(body.instructions)
        print('=== %s::%s  rva=%s  insns=%d ===' % (tname, mname, hex(m.Rva), len(ins)))
        # 解析局部变量名
        for i2 in ins:
            if lo is not None and i2.offset < lo:
                continue
            if hi is not None and i2.offset > hi:
                break
            print('  IL_%05x %-12s %s' % (i2.offset, i2.opcode.name, self.describe(i2)))
        return ins


if __name__ == '__main__':
    dll = sys.argv[1]
    t = sys.argv[2]
    m = sys.argv[3]
    lo = int(sys.argv[4], 16) if len(sys.argv) > 4 else None
    hi = int(sys.argv[5], 16) if len(sys.argv) > 5 else None
    Ill(dll).dump(t, m, lo, hi)
