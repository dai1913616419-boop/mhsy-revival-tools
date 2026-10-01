"""dncil 反汇编 + #US 字符串 + MemberRef/TypeRef 正确解析。
用法: disasm3.py <dll> <TypeName> [MethodName] [--full]
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dnfile
from dncil.cil.body import CilMethodBody
from dncil.cil.body.reader import CilMethodBodyReaderBase
from dncil.cil.error import MethodBodyFormatError
from dncil.clr.token import Token, StringToken
from usheap import USResolver

class Reader(CilMethodBodyReaderBase):
    def __init__(self, pe, rva):
        self.pe = pe
        self.offset = pe.get_offset_from_rva(rva)
    def read(self, n):
        d = self.pe.__data__[self.offset:self.offset+n]; self.offset += n; return d
    def tell(self): return self.offset
    def seek(self, o): self.offset = o; return o

def build(pe):
    mdt = pe.net.mdtables
    TN = {i: ((t.TypeNamespace.value or '') + '.' + t.TypeName.value).lstrip('.')
          for i, t in enumerate(mdt.TypeDef.rows, 1)}
    MN = {i: str(m.Name) for i, m in enumerate(mdt.MethodDef.rows, 1)}
    FN = {i: str(f.Name) for i, f in enumerate(mdt.Field.rows, 1)}
    # TypeRef: rid -> 全名
    TRN = {}
    for i, tr in enumerate(mdt.TypeRef.rows, 1):
        TRN[i] = ((tr.TypeNamespace.value or '') + '.' + tr.TypeName.value).lstrip('.')
    # MemberRef: rid -> "Owner::Name"
    MR = {}
    for i, mr in enumerate(mdt.MemberRef.rows, 1):
        name = str(mr.Name)
        cls = mr.Class.row if hasattr(mr.Class, 'row') else mr.Class
        owner = '?'
        try:
            tbl = mr.Class.table.name if hasattr(mr.Class, 'table') else ''
        except Exception:
            tbl = ''
        if 'TypeRef' in str(tbl):
            owner = TRN.get(cls.row_index if hasattr(cls, 'row_index') else cls, '?')
        elif 'TypeDef' in str(tbl):
            owner = TN.get(cls.row_index if hasattr(cls, 'row_index') else cls, '?')
        MR[i] = '%s::%s' % (owner, name)
    TS = {}
    for i, ts in enumerate(mdt.TypeSpec.rows, 1):
        TS[i] = 'TypeSpec%d' % i
    return TN, MN, FN, MR, TRN, TS

def disasm_at_rva(path, rva_sel):
    """按 RVA 直接反汇编（混淆后类名大量重复时很有用）。"""
    from dncil.cil.body import CilMethodBody
    from dncil.cil.body.reader import CilMethodBodyReaderBase
    from dncil.clr.token import Token, StringToken
    pe = dnfile.dnPE(path)
    us = USResolver(pe)
    TN, MN, FN, MR, TRN, TS = build(pe)

    def resolve(tok):
        if isinstance(tok, StringToken):
            v = us.get(tok.rid)
            return '"%s"' % v if v is not None else "str@%s" % tok.rid
        tb = (tok.value >> 24) & 0xFF
        rid = tok.value & 0xFFFFFF
        if tb == 0x06: return MN.get(rid, "md:%d" % rid)
        if tb == 0x0A: return MR.get(rid, "mr:%d" % rid)
        if tb == 0x0B: return "sig:%d" % rid
        if tb == 0x01: return TRN.get(rid, "tr:%d" % rid)
        if tb == 0x02: return TN.get(rid, "td:%d" % rid)
        if tb == 0x04: return "fld:" + FN.get(rid, str(rid))
        if tb == 0x1B: return TS.get(rid, "ts:%d" % rid)
        return "tok:0x%08x" % tok.value

    class R(CilMethodBodyReaderBase):
        def __init__(self, pe, rva):
            self.pe = pe
            self.offset = pe.get_offset_from_rva(rva)
        def read(self, n):
            d = self.pe.__data__[self.offset:self.offset + n]
            self.offset += n
            return d
        def tell(self): return self.offset
        def seek(self, o): self.offset = o; return o

    print("=== RVA 0x%x ===" % rva_sel)
    body = CilMethodBody(R(pe, rva_sel))
    for ins in body.instructions:
        operand = ins.operand
        if isinstance(operand, Token):
            operand = resolve(operand)
        elif operand is None:
            operand = ""
        else:
            operand = str(operand)
        print("  IL_%04x: %-14s %s" % (ins.offset, ins.opcode.name,
              str(operand).encode('utf-8', 'backslashreplace').decode('utf-8') if operand else ""))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    opts = [a for a in sys.argv[1:] if a.startswith('--')]
    for o in opts:
        if o.startswith('--rva='):
            disasm_at_rva(args[0], int(o.split('=', 1)[1], 0))
            return
    path, tname = args[0], args[1]
    mname = args[2] if len(args) > 2 else None
    pe = dnfile.dnPE(path)
    us = USResolver(pe)
    mdt = pe.net.mdtables
    TN, MN, FN, MR, TRN, TS = build(pe)

    def resolve(tok):
        if isinstance(tok, StringToken):
            v = us.get(tok.rid)
            return '"%s"' % v if v is not None else "str@%s" % tok.rid
        tb = (tok.value >> 24) & 0xFF
        rid = tok.value & 0xFFFFFF
        if tb == 0x06: return MN.get(rid, "md:%d" % rid)
        if tb == 0x0A: return MR.get(rid, "mr:%d" % rid)      # MemberRef
        if tb == 0x0B: return "sig:%d" % rid                   # MethodSpec
        if tb == 0x01: return TRN.get(rid, "tr:%d" % rid)      # TypeRef
        if tb == 0x02: return TN.get(rid, "td:%d" % rid)       # TypeDef
        if tb == 0x04: return "fld:" + FN.get(rid, str(rid))   # Field
        if tb == 0x1B: return TS.get(rid, "ts:%d" % rid)       # TypeSpec
        return "tok:0x%08x" % tok.value

    found = False
    for t in mdt.TypeDef.rows:
        tn = ((t.TypeNamespace.value or '') + '.' + t.TypeName.value).lstrip('.')
        if tn != tname and str(t.TypeName) != tname:
            continue
        for m in (t.MethodList or []):
            r = m.row if hasattr(m, 'row') else m
            if mname is None or str(r.Name) == mname:
                found = True
                print("\n=== %s::%s  rva=0x%x ===" % (tn, r.Name, r.Rva))
                try:
                    body = CilMethodBody(Reader(pe, r.Rva))
                    for ins in body.instructions:
                        op = ins.opcode.name; operand = ins.operand
                        if isinstance(operand, Token): operand = resolve(operand)
                        elif operand is None: operand = ""
                        else: operand = str(operand)
                        print("  IL_%04x: %-14s %s" % (ins.offset, op, operand))
                except MethodBodyFormatError as e:
                    print("  [无方法体]", e)
                except Exception as e:
                    print("  ERR", type(e).__name__, e)
if __name__ == "__main__":
    main()

