"""dncil 反汇编 + #US/#Blob 解析。用法: disasm2.py <dll> <TypeName> [MethodName]"""
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

def main():
    path, tname = sys.argv[1], sys.argv[2]
    mname = sys.argv[3] if len(sys.argv) > 3 else None
    pe = dnfile.dnPE(path)
    us = USResolver(pe)
    mdt = pe.net.mdtables

    TN = {i: str(t.TypeName) for i, t in enumerate(mdt.TypeDef.rows, 1)}
    MN = {i: str(m.Name) for i, m in enumerate(mdt.MethodDef.rows, 1)}
    FN = {i: str(f.Name) for i, f in enumerate(mdt.Field.rows, 1)}
    def tname_of(rid): return TN.get(rid, "?")
    def mname_of(rid): return MN.get(rid, "?")
    def fname_of(rid): return FN.get(rid, "?")

    def resolve(tok):
        if isinstance(tok, StringToken):
            v = us.get(tok.rid)
            return '"%s"' % v if v is not None else "str@%s" % tok.rid
        tb = (tok.value >> 24) & 0xFF
        rid = tok.value & 0xFFFFFF
        if tb == 0x06: return mname_of(rid)
        if tb == 0x0A: return mname_of(rid)     # MemberRef -> 近似
        if tb == 0x04: return "fld:" + fname_of(rid)
        if tb == 0x02: return tname_of(rid)
        return "tok:0x%08x" % tok.value

    rows = [r for r in mdt.MethodDef.rows]
    targets = []
    for t in mdt.TypeDef.rows:
        if str(t.TypeName) != tname: continue
        for m in (t.MethodList or []):
            r = m.row if hasattr(m, "row") else m
            if mname is None or str(r.Name) == mname:
                targets.append(r)
    if not targets:
        print("未找到", tname, mname); return
    for r in targets:
        print(f"\n=== {tname}::{r.Name}  rva=0x{r.Rva:x} ===")
        try:
            body = CilMethodBody(Reader(pe, r.Rva))
            for ins in body.instructions:
                op = ins.opcode.name; operand = ins.operand
                if isinstance(operand, Token): operand = resolve(operand)
                elif operand is None: operand = ""
                else: operand = str(operand)
                print(f"  IL_{ins.offset:04x}: {op:<14} {operand}")
        except MethodBodyFormatError as e:
            print("  [无方法体]", e)
        except Exception as e:
            print("  ERR", type(e).__name__, e)

main()
