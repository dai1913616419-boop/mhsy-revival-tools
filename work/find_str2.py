# -*- coding: utf-8 -*-
"""按中文关键字反查 #US 字符串引用（避免 shell 中文参数编码问题）。
用法: find_str2.py <关键字（写在源码里）>
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dnfile
from dncil.cil.body import CilMethodBody
from dncil.clr.token import StringToken
from usheap import parse_us
from disasm3 import Reader

DLL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'apk', 'Client_4201.dll')

# 关键字表（直接写在源码，避免命令行编码问题）
KEYWORDS = [
    '\u4e3b\u5c06\u4e0d\u80fd\u4e3a\u7a7a',          # 主将不能为空
    '\u9635\u5bb9',                                    # 阵容
    '\u4e0a\u9635',                                    # 上阵
]


def main():
    pe = dnfile.dnPE(DLL)
    us = parse_us(pe.net.user_strings.__data__)
    mdt = pe.net.mdtables
    for kw in KEYWORDS:
        targets = set(o for o, s in us.items() if kw in s)
        print('=== 关键字 %r 命中 #US 偏移: %s' % (kw, sorted(targets)))
        for o in sorted(targets):
            print('     "%s"' % us[o][:70])
        if not targets:
            continue
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
                        print('  0x%06x  %s::%s' % (r.Rva, tn, r.Name))
                        break
        print()


main()
