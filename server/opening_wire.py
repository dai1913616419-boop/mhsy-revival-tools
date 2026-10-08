"""Opening protocol builders. Wire choices follow the actual generated client serializers."""
from datetime import datetime, timedelta
import struct

import proto
import game_server as legacy


def fields(body: bytes):
    def integer(pos):
        value = 0
        for shift in range(0, 70, 7):
            if pos >= len(body):
                raise ValueError('Truncated protobuf integer')
            byte = body[pos]; pos += 1
            value |= (byte & 127) << shift
            if byte < 128:
                return value, pos
        raise ValueError('Overlong protobuf integer')
    result = []
    pos = 0
    while pos < len(body):
        tag, pos = integer(pos)
        number, wire = tag >> 3, tag & 7
        if not number:
            raise ValueError('Invalid protobuf field number')
        if wire == 0:
            value, pos = integer(pos)
        elif wire == 2:
            size, pos = integer(pos)
            if size > len(body) - pos:
                raise ValueError('Truncated protobuf bytes')
            value = body[pos:pos + size]; pos += size
        elif wire in (1, 5):
            size = 8 if wire == 1 else 4
            if size > len(body) - pos:
                raise ValueError('Truncated fixed-width value')
            value = body[pos:pos + size]; pos += size
        else:
            raise ValueError(f'Unsupported protobuf wire type {wire}')
        result.append((number, wire, value))
    return result


def first(body, number, default=0):
    return next((v for n, w, v in fields(body) if n == number), default)


def hero(h):
    out = proto.s_field(1, h['guid'])
    for n, value in ((2, h['index']), (3, h['level']), (4, h['stage']), (5, h.get('xp', 0)), (6, h['stars'])):
        out += proto.v_field_raw(n, value)
    for n, value in enumerate(h.get('params', [0, 0, 0, 0]), 7):
        out += proto.v_field_raw(n, value)
    for tag, key in ((11, 'MJ'), (12, 'A'), (13, 'B'), (14, 'BD')):
        out += proto.v_field_raw(tag, h.get('skills', {}).get(key, 1))
    return out


def formation(kind, slots):
    out = proto.v_field_raw(1, kind)
    # Empty positions are semantically meaningful; proto.s_field omits them.
    for slot in slots:
        raw = slot.encode('utf-8')
        out += proto.tag(2, 2) + proto.varint(len(raw)) + raw
    return out


def player(d, account=None):
    out = proto.v_field(1, 1) + proto.s_field(2, account or d['account'])
    for n, v in ((3, d['level']), (5, d['xp']), (6, d['stamina']), (7, d['gems']),
                 (8, d['coins']), (9, d['last_normal_region']), (10, d['last_elite_region']),
                 (11, 10), (12, 20), (22, 1), (23, 0), (35, d['res_id'] - 17)):
        out += proto.v_field_raw(n, v)
    # Actual next-day deadline, not the demo's artificial 120-second popup.
    created = datetime.strptime(d['created_at'], '%Y-%m-%d %H:%M:%S')
    deadline = (created + timedelta(days=1)).replace(hour=0, minute=0, second=0)
    out += proto.v_field_raw(36, max(0, int((deadline - datetime.now()).total_seconds())))
    out += proto.s_field(48, d['created_at'])
    out += legacy.build_resource_fb_list()
    for h in d['heroes'].values():
        out += proto.m_field(101, hero(h))
    for name, count in d['goods'].items():
        out += proto.m_field(102, proto.s_field(1, name) + proto.v_field_raw(2, count))
    for key, stars in d['region_stars'].items():
        out += proto.m_field(103, proto.v_field(1, int(key)) + proto.v_field(2, stars))
    out += proto.s_field(30, d['draws'].get('silver_time', ''))
    out += proto.s_field(31, d['draws'].get('gold_time', ''))
    out += proto.v_field_raw(32, 5 - d['draws']['silver'])
    for name, value in d['vars'].items():
        out += proto.m_field(109, proto.s_field(1, name) + proto.s_field(2, value))
    return out


def main_player(d, account=None):
    return (proto.v_field(1, 1) + proto.v_field(2, d['res_id'])
            + proto.s_field(3, d['role_name']) + proto.m_field(4, player(d, account)))


def enter(d):
    return (proto.v_field(1, 1) + proto.v_field_raw(2, int(d['novice_completed']))
            + proto.v_field(4, d['res_id'] - 17)
            + proto.s_field(5, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))


def tasks(entries):
    return b''.join(proto.m_field(1, proto.v_field(1, tid)
                  + proto.v_field_raw(2, count) + proto.v_field_raw(3, int(delete)))
                  for tid, count, delete in entries)


def player_attribute(kind, value):
    return proto.v_field(1, kind) + proto.v_field_raw(2, value)


def hero_attribute(guid, kind, value):
    return proto.s_field(1, guid) + proto.v_field(2, kind) + proto.v_field_raw(3, value)


def goods(name, count):
    return proto.s_field(1, name) + proto.v_field_raw(2, count)


def fb_info(region, awards):
    return (proto.v_field(1, region) + proto.v_field(2, awards['coins'])
            + proto.v_field(3, awards['xp']) + proto.v_field(4, awards['hero_xp'])
            + proto.v_field_raw(8, 0))


def empty_arena_info():
    # The client unconditionally dereferences TargetBriefInfos; an absent wrapper is not an empty list.
    return b''.join(proto.v_field_raw(n, 0) for n in (1, 2, 3, 4)) + b'\x32\x00'


def draw_counters(d):
    return (proto.s_field(1, d['draws'].get('silver_time', ''))
            + proto.s_field(2, d['draws'].get('gold_time', ''))
            + proto.v_field_raw(3, 5 - d['draws']['silver']) + proto.v_field_raw(4, 0))


def draw_result(kind):
    award = (proto.v_field(1, 3) + proto.m_field(4, goods('GOODS48', 1))) if kind == 'silver' else (
        proto.v_field(1, 2) + proto.m_field(3, proto.v_field(1, 31)))
    return (proto.v_field(1, 1 if kind == 'silver' else 2) + proto.v_field(2, 1)
            + proto.m_field(3, award))
