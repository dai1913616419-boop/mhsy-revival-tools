"""完整 token 解析反汇编: disasm_full.py <dll> <rva_hex> [rva2 ...]
解析 ldstr(#US)/MemberRef/MethodDef/Field/TypeDef token, 输出到 stdout。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dnfile
from dncil.cil.body import CilMethodBody
from dncil.clr.token import Token
from disasm3 import Reader
from usheap import USResolver


def main():
    dll = sys.argv[1]
    pe = dnfile.dnPE(dll)
    us = USResolver(pe)
    mdt = pe.net.mdtables
    MR = {0x0A000000 | i: str(mr.Name) for i, mr in enumerate(mdt.MemberRef.rows, 1)}
    MD = {}
    for ti, t in enumerate(mdt.TypeDef.rows, 1):
        tn = (t.TypeNamespace.value or '') + '.' + (t.TypeName.value or '')
        for m in (t.MethodList or []):
            r = m.row
            if r.Rva:
                MD[r.Rva] = tn + '::' + str(r.Name)
    FD = {0x04000000 | i: str(f.Name) for i, f in enumerate(mdt.Field.rows, 1)}
    TD = {0x02000000 | i: (t.TypeNamespace.value or '') + '.' + (t.TypeName.value or '')
          for i, t in enumerate(mdt.TypeDef.rows, 1)}

    def fmt(op):
        if isinstance(op, Token):
            raw = (op.table << 24) | op.rid if hasattr(op, 'table') else 0
            hi = raw >> 24
            if hi == 0x70:
                v = us.get(raw & 0xFFFFFF)
                return 'str:' + (repr(v)[:70] if v is not None else hex(raw))
            if hi == 0x0A:
                return MR.get(raw, hex(raw))
            if hi == 0x06:
                r = mdt.MethodDef.rows[(raw & 0xFFFFFF) - 1]
                return 'mdef:' + (MD.get(r.Rva) or str(r.Name))
            if hi == 0x04:
                return 'fld:' + FD.get(raw, hex(raw))
            if hi == 0x02:
                return 'type:' + TD.get(raw, hex(raw))
            return hex(raw)
        return str(op)

    for a in sys.argv[2:]:
        rva = int(a, 16)
        body = CilMethodBody(Reader(pe, rva))
        print('=== %s %s (%d insns)' % (dll, hex(rva), len(body.instructions)))
        for ins in body.instructions:
            print('  %d %s %s' % (ins.offset, ins.opcode.name, fmt(ins.operand)))


if __name__ == '__main__':
    main()
