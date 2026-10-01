#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""极简 protobuf 编码器（够用即可，配合 protobuf-net 反序列化）。

protobuf-net 对未设置字段使用默认值，因此服务端只需写出关心的字段。
"""
import struct


def varint(n):
    if n < 0:
        n += 1 << 64
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def tag(field, wire):
    return varint((field << 3) | wire)


def v_field(field, value):
    """varint 字段（int32/int64/bool/enum）。
    ⚠ protobuf 惯例：0 值字段不序列化 -> 整个 body 可能变成空字节。
    对"客户端 Deserialize<T>(空) 可能返回 null 并 NRE"的场景
    （如 4602 CCMsgZBZInfo），必须用 v_field_raw 显式写出。"""
    if value == 0:
        return b""
    return tag(field, 0) + varint(int(value))


def v_field_raw(field, value):
    """varint 字段，**即使 value==0 也写出 tag+0**。
    用途：保证消息 body 非空，避免客户端
    `Deserialize<T>(空字节)` 返回 null 导致后续 ldfld NRE。
    语义与 v_field(field,0) 完全等价（protobuf 默认值），只是占用 2 字节。"""
    return tag(field, 0) + varint(int(value))


def s_field(field, text):
    """string / bytes 字段。"""
    if text is None:
        return b""
    if isinstance(text, str):
        text = text.encode("utf-8")
    if not text:
        return b""
    return tag(field, 2) + varint(len(text)) + text


def m_field(field, payload):
    """嵌套消息字段。"""
    if not payload:
        return b""
    return tag(field, 2) + varint(len(payload)) + payload


def f32_field(field, value):
    if value == 0.0:
        return b""
    return tag(field, 5) + struct.pack("<f", float(value))


def i32_field(field, value):
    """DataFormat=2 的 int32 字段（契约 type=raw:280008）——必须定长整数，
    不是 float！用 float 编码会让 protobuf-net 读出错值/结构异常。"""
    if value == 0:
        return b""
    return tag(field, 5) + struct.pack("<i", int(value))


def f64_field(field, value):
    if value == 0.0:
        return b""
    return tag(field, 1) + struct.pack("<d", float(value))


def packed(field, values):
    """repeated int32 的 packed 编码（protobuf-net 两种都认）。"""
    if not values:
        return b""
    body = b"".join(varint(int(v)) for v in values)
    return tag(field, 2) + varint(len(body)) + body


def repeated_msg(field, items):
    """repeated 嵌套消息（非 packed，每个元素独立 tag+len）。"""
    return b"".join(m_field(field, it) for it in items)


def repeated_str(field, items):
    return b"".join(s_field(field, it) for it in items)
