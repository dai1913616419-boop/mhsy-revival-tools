"""扫描 Client DLL，找出引用指定 #US 字符串的所有方法。
用法: find_str_refs.py <dll> <关键字1> [关键字2 ...]
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dnfile
from dncil.cil.body import CilMethodBody
from dncil.cil.error import MethodBodyFormatError
from dncil.clr.token import Token, StringToken
from usheap import USResolver, parse_us
from disasm3 import Reader


def main():
    path = sys.argv[1]
    kws = [k.lower() for k in sys.argv[2:]]
    pe = dnfile.dnPE(path)
    us = parse_us(pe.net.user_strings.__data__)
    # 目标 us 偏移
    targets = set()
    for off, s in us.items():
        sl = s.lower()
        if any(k in sl for k in kws):
            targets.add(off)
    print("目标 #US 偏移:", sorted(targets))
    print("样例:", [us[o][:60] for o in sorted(targets)][:10])
    mdt = pe.net.mdtables
    TN = {i: ((t.TypeNamespace.value or '') + '.' + t.TypeName.value).lstrip('.')
          for i, t in enumerate(mdt.TypeDef.rows, 1)}
    for t in mdt.TypeDef.rows:
        tn = ((t.TypeNamespace.value or '') + '.' + t.TypeName.value).lstrip('.')
        for m in (t.MethodList or []):
            r = m.row if hasattr(m, 'row') else m
            if not r.Rva:
                continue
            try:
                body = CilMethodBody(Reader(pe, r.Rva))
            except Exception:
                continue
            for ins in body.instructions:
                if isinstance(ins.operand, StringToken) and ins.operand.rid in targets:
                    print("0x%06x  %s::%s   ->  \"%s\"" % (
                        r.Rva, tn, r.Name, us.get(ins.operand.rid, '?')[:80]))
                    break


main()
