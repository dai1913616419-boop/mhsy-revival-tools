"""用 dncil 反汇编指定方法的 IL。

用法:
  python disasm.py <dll> <TypeName> [MethodName]
未给 MethodName 时列出该类型的所有方法。
"""
import sys
import dnfile
from dncil.cil.body import CilMethodBody
from dncil.cil.body.reader import CilMethodBodyReaderBase
from dncil.cil.error import MethodBodyFormatError
from dncil.clr.token import Token, StringToken


class Reader(CilMethodBodyReaderBase):
    def __init__(self, pe, rva):
        self.pe = pe
        self.offset = pe.get_offset_from_rva(rva)

    def read(self, n):
        data = self.pe.__data__[self.offset:self.offset + n]
        self.offset += n
        return data

    def tell(self):
        return self.offset

    def seek(self, off):
        self.offset = off
        return off


def resolve(pe, token):
    if isinstance(token, StringToken):
        try:
            return '"%s"' % pe.net.user_strings.get_us(token.rid).value
        except Exception:
            return "str#%s" % token.rid
    try:
        r = pe.net.mdtables.tables_by_index.get(token.table, None)
    except Exception:
        r = None
    return "tok:0x%08x" % token.value


def methods_of(pe, tname):
    out = []
    for t in pe.net.mdtables.TypeDef.rows:
        if str(t.TypeName) == tname:
            for m in (t.MethodList or []):
                r = m.row if hasattr(m, "row") else m
                out.append(r)
    return out


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "carved/CAB-Client_0000332b.dll"
    tname = sys.argv[2] if len(sys.argv) > 2 else "RegionPropertyCfgMgr"
    mname = sys.argv[3] if len(sys.argv) > 3 else None
    pe = dnfile.dnPE(path)
    ms = methods_of(pe, tname)
    print(f"类型 {tname}: {len(ms)} 个方法")
    if not mname:
        for r in ms:
            print("   ", str(r.Name), "rva=0x%x" % r.Rva)
        return
    targets = [r for r in ms if str(r.Name) == mname]
    if not targets:
        print("未找到方法", mname)
        return
    for r in targets:
        print(f"\n=== {tname}.{mname}  rva=0x{r.Rva:x} ===")
        try:
            body = CilMethodBody(Reader(pe, r.Rva))
            for ins in body.instructions:
                op = ins.opcode.name
                operand = ins.operand
                if isinstance(operand, Token):
                    operand = resolve(pe, operand)
                elif operand is None:
                    operand = ""
                else:
                    operand = str(operand)
                print(f"   IL_{ins.offset:04x}: {op:<14} {operand}")
        except MethodBodyFormatError as e:
            print("   [无方法体/抽象]", e)
        except Exception as e:
            print("   ERR", type(e).__name__, e)


if __name__ == "__main__":
    main()
