"""resolve.py <dll> <rva>  列出方法内所有 MemberRef/MethodSpec 的完整类型.成员"""
import sys, dnfile
from dncil.cil.body import CilMethodBody
from disasm3 import Reader
pe = dnfile.dnPE(sys.argv[1]); mdt = pe.net.mdtables
rva = int(sys.argv[2], 16)
body = CilMethodBody(Reader(pe, rva))

def typename_of_mr(mr):
    try:
        c = mr.Class
        # Class 是 MemberRefParent: 0x01 TypeRef, 0x02 TypeDef, 0x1B TypeSpec, 0x1A MethodDef
        row = c.row
        for attr in ('TypeNamespace','TypeName'):
            pass
        ns = getattr(row, 'TypeNamespace', None)
        nm = getattr(row, 'TypeName', None)
        if nm is not None:
            return ((ns.value if ns else '') + '.' + (nm.value if nm else ''))
        return str(row)
    except Exception as e:
        return '?'

def walk(ops):
    for op in ops:
        if isinstance(op.operand, dnfile.mdtable.MemberRefRow):
            mr = op.operand
            print(f'  {op.opcode.name:<10} {typename_of_mr(mr)}::{mr.Name}')
        elif hasattr(op.operand, 'rows') or type(op.operand).__name__=='MethodSpecRow':
            ms = op.operand
            try:
                m = ms.Method.row
                nm = getattr(m,'Name',None)
                print(f'  {op.opcode.name:<10} MethodSpec -> {nm}')
            except Exception as e:
                print(f'  {op.opcode.name:<10} MethodSpec ? {e}')
walk(body.instructions)
