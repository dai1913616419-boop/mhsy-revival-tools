"""Separate opening-mode server; does not load/write the legacy demo save.

Run: python opening_server.py --profile profiles/opening.json --port 9003
"""
import argparse
from pathlib import Path
import socket
import struct
import threading
import zlib

import game_server as legacy
import opening_wire as wire
import opening_data as data
from opening_state import OpeningStore
import proto

MAX_FRAME = 1024 * 1024


class OpeningClient(legacy.Client):
    def __init__(self, conn, addr, store):
        super().__init__(conn, addr)
        self.store = store
        self.refresh()
        self.cur_region = 0
        self.ready = False

    def refresh(self):
        d = self.store.snapshot()
        self.account, self.role_name, self.res_id, self.level = (
            d['account'], d['role_name'], d['res_id'], d['level'])
        return d

    def send(self, msgid, body=b''):
        with self.send_lock:
            self.serial = (self.serial + 1) & 0xffff
            self.conn.sendall(legacy.make_frame(msgid, body, self.serial))
            if msgid != 3:
                legacy.log(f'[opening] send {msgid} {body.hex()}')

    def get_formation(self, kind):
        d = self.store.snapshot()
        return d['formations'].get(str(kind), d['formations'].get('0', [''] * 5))

    def set_formation(self, kind, slots):
        self.store.save_formation(kind, slots)

    def push_tasks(self):
        d = self.store.snapshot()
        # Only the opening quest; claimed quests must stay removed after reconnect.
        entries = [] if 1 in d['claimed_quests'] else [(1, d['quest_progress'].get('1', 0), False)]
        self.send(1103, wire.tasks(entries))
        self.send(1101, b'')

    def abort_unfinished_story(self):
        d = self.store.snapshot()
        b = d['battle']
        if b and not b['settled'] and b['region'] in (1001, 1002, 1003):
            self.store.settle_battle(b['id'], False)
            legacy.log('[opening] interrupted story aborted with configured one-stamina cost')
            return True
        return False

    def initial_player(self):
        d = self.refresh()
        self.cur_region = 1 if d['novice_completed'] else 99
        born = legacy.get_region_born_pos(self.cur_region)
        if born:
            self.send(103, legacy.build_set_main_city_born_pos(*born))
        self.send(102, wire.main_player(d, self.account))
        self.send(201, wire.formation(0, self.get_formation(0)))
        self.send(450, legacy.build_resource_fb_update())
        self.send(4602, legacy.build_zbz_info())
        if self.cur_region == 99 and not d['battle']:
            self.store.begin_battle(99)

    def to_city(self):
        born = legacy.get_region_born_pos(1)
        self.send(103, legacy.build_set_main_city_born_pos(*born))
        self.send(107, proto.v_field(1, 1))
        self.cur_region, self.ready = 1, False

    def push_balances(self, d):
        for kind, key in ((6, 'level'), (1, 'xp'), (3, 'coins'), (4, 'gems'), (2, 'stamina')):
            self.send(501, wire.player_attribute(kind, d[key]))
        for h in d['heroes'].values():
            self.send(601, wire.hero_attribute(h['guid'], 2, h['level']))
            self.send(601, wire.hero_attribute(h['guid'], 1, h.get('xp', 0)))

    def story_enter(self, body):
        region, difficulty = wire.first(body, 1, 0), wire.first(body, 2, 1)
        if region not in (1001, 1002, 1003) or difficulty != 1:
            raise ValueError('Only normal story1001–1003 are supported in this build')
        d = self.store.snapshot()
        first_clear = str(region * 10 + difficulty) not in d['region_stars']
        awards = data.rewards(region, difficulty, first_clear)
        self.store.begin_battle(region, difficulty)
        with self.store.transaction() as d:
            d['battle']['awards'] = awards
        self.send(501, wire.player_attribute(2, self.store.snapshot()['stamina']))
        # Client caches FBInfo at scene construction, before its104 ready request.
        self.send(401, wire.fb_info(region, awards))
        born = legacy.get_region_born_pos(region)
        self.send(103, legacy.build_set_main_city_born_pos(*born))
        self.send(107, proto.v_field(1, region))
        self.cur_region, self.ready = region, False

    def story_result(self, body):
        result = wire.first(body, 1, 2)
        if result not in (1, 2):
            raise ValueError('Unknown battle outcome')
        won = result == 1
        stars = wire.first(body, 2, 0)
        if won and stars not in (1, 2, 3):
            raise ValueError('Victory requires the client-reported star count')
        before = self.store.snapshot()
        b = before['battle']
        if not b or b['region'] not in (1001, 1002, 1003):
            raise ValueError('Story result has no matching battle')
        if b['settled']:
            won = b['won']
            result = 1 if won else 2
            stars = b.get('stars', 0)
        elif not self.ready or self.cur_region != b['region']:
            raise ValueError('Story result arrived before the active scene was ready')
        awards = b.get('awards', {})
        is_new = self.store.settle_battle(b['id'], won, stars=stars,
            coins=awards.get('coins', 0), xp=awards.get('xp', 0),
            goods=awards.get('goods', {}), hero_xp=awards.get('hero_xp', 0),
            player_levels=data.PLAYER_LEVELS, hero_levels=data.HERO_LEVELS)
        d = self.refresh()
        if is_new:
            self.push_balances(d)
            for name in awards.get('goods', {}):
                self.send(301, wire.goods(name, d['goods'].get(name, 0)))
            if won and b['region'] == 1003:
                self.send(1104, wire.tasks([(1, 1, False)]))
        self.send(1001, proto.v_field_raw(1, result) + proto.v_field_raw(2, stars))

    def handle(self, msgid, body):
        if msgid not in (3, 103):
            legacy.log(f'[opening] request {msgid} {body.hex() if msgid != 101 else "<credentials redacted>"}')
        if msgid == 1:
            self.send(1, proto.v_field(1, 1))
        elif msgid == 3:
            self.send(3, body)
        elif msgid == 101:
            acc, _, _, _, _ = legacy.parse_account_enter(body)
            if acc:
                self.account = acc
                with self.store.transaction() as d:
                    d['account'] = acc
            self.abort_unfinished_story()
            d = self.refresh()
            self.send(108, legacy.build_account_enter_check_ret(1, self.account, '1'))
            if not d['role_name']:
                # 101 would select an automatic scene; no-role accounts need create state instead.
                self.send(1301, proto.v_field_raw(1, 0))
            else:
                self.send(101, wire.enter(d))
        elif msgid == 1001:
            name = wire.first(body, 1, b'').decode('utf-8')
            selection = wire.first(body, 2, 0)
            d = self.store.create_role(name, selection)
            self.refresh()
            self.send(1302, proto.v_field_raw(1, 0))
            self.send(101, wire.enter(d))
        elif msgid == 102:
            self.initial_player()
        elif msgid == 5401:
            self.send(5401, b'')
        elif msgid == 5402:
            pass  # No registered client handler; request is informational.
        elif msgid == 201:
            kind = wire.first(body, 1, 0)
            self.send(201, wire.formation(kind, self.get_formation(kind)))
        elif msgid == 202:
            kind = wire.first(body, 1, 0)
            slots = [v.decode('utf-8') for n, w, v in wire.fields(body) if n == 2 and w == 2]
            self.set_formation(kind, slots)
        elif msgid == 301:
            self.story_enter(body)
        elif msgid == 302:
            self.story_result(body)
        elif msgid in (2201, 2202):
            if not wire.first(body, 1, 0):
                raise ValueError('Opening mode only supports the guided single draws')
            kind = 'silver' if msgid == 2201 else 'gold'
            d, is_new = self.store.recruit(kind)
            if kind == 'silver':
                self.send(301, wire.goods('GOODS48', d['goods']['GOODS48']))
            elif is_new:
                self.send(1204, proto.m_field(1, wire.hero(d['heroes']['hero31'])) + proto.v_field_raw(2, 0))
            self.send(2401, wire.draw_result(kind))
            self.send(2402, wire.draw_counters(d))
        elif msgid == 704:
            task_id = wire.first(body, 1, 0)
            d, is_new = self.store.claim_quest(task_id)
            if is_new:
                self.send(501, wire.player_attribute(3, d['coins']))
                self.send(501, wire.player_attribute(4, d['gems']))
                self.send(301, wire.goods('GOODS104', d['goods']['GOODS104']))
            self.send(1104, wire.tasks([(task_id, 1, True)]))
        elif msgid == 904:
            guid = wire.first(body, 1, b'').decode('utf-8')
            slot = wire.first(body, 2, 0)
            d = self.store.advance_slot(guid, slot)
            material = ('GOODS42', 'GOODS51', 'GOODS51', 'GOODS48')[slot - 1]
            self.send(301, wire.goods(material, d['goods'][material]))
            self.send(601, wire.hero_attribute(guid, 4 + slot, 1))
        elif msgid == 905:
            guid = wire.first(body, 1, b'').decode('utf-8')
            d = self.store.advance_hero(guid)
            self.send(501, wire.player_attribute(3, d['coins']))
            self.send(601, wire.hero_attribute(guid, 3, d['heroes'][guid]['stage']))
        elif msgid == 1801:
            name = wire.first(body, 1, b'').decode('utf-8')
            value = wire.first(body, 2, b'').decode('utf-8')
            if wire.first(body, 3, 0):
                with self.store.transaction() as d:
                    d['vars'].pop(name, None)
                    d.setdefault('pending_vars', {}).pop(name, None)
            else:
                self.store.set_var(name, value)
        elif msgid in (701, 703):
            if msgid == 703:
                self.push_tasks()
            else:
                self.send(1101, b'')
        elif msgid == 103:
            self.ready = True
        elif msgid == 104:
            self.cur_region = wire.first(body, 1, self.cur_region)
            born = legacy.get_region_born_pos(self.cur_region)
            if born:
                self.send(103, legacy.build_set_main_city_born_pos(*born))
            self.ready = True
        elif msgid == 304:
            # Also sent during completed-account login, before MainPlayer exists.
            # The normal102 flow handles that initial city; do not race it with107.
            if self.cur_region in (0, 1):
                return
            d = self.store.snapshot()
            if self.cur_region == 99 and not d['novice_completed']:
                b = d['battle']
                if not b or b['region'] != 99:
                    raise ValueError('Novice completion without an active novice session')
                self.store.settle_battle(b['id'], True)
                legacy.log('[opening] persisted actual novice completion')
            elif self.cur_region in (1001, 1002, 1003) and self.abort_unfinished_story():
                self.push_balances(self.refresh())
            self.to_city()
        elif msgid == 601:
            self.abort_unfinished_story()
            d = self.refresh()
            # Reconnect snapshot is profile-based, never the demo level30/roster.
            out = proto.v_field(1, 1) + proto.m_field(2, wire.player(d, self.account))
            from datetime import datetime
            out += proto.s_field(3, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            self.send(901, out)
            self.send(201, wire.formation(0, self.get_formation(0)))
            self.send(450, legacy.build_resource_fb_update())
            self.send(4602, legacy.build_zbz_info())
            if d['novice_completed']:
                self.to_city()
            else:
                self.cur_region, self.ready = 99, False
                self.send(103, legacy.build_set_main_city_born_pos(*legacy.get_region_born_pos(99)))
                self.send(107, proto.v_field(1, 99))
        elif msgid == 2001:
            self.send(2001, wire.empty_arena_info())
        else:
            legacy.log(f'[opening] UNIMPLEMENTED request {msgid} {body.hex()}')

    def run(self):
        self.conn.settimeout(30)
        try:
            while not self.closed:
                part = self.conn.recv(65536)
                if not part:
                    break
                self.buf += part
                while len(self.buf) >= 4:
                    total = struct.unpack_from('<I', self.buf)[0]
                    if total < 12 or total > MAX_FRAME:
                        raise ValueError('Invalid frame length')
                    if len(self.buf) < total:
                        break
                    frame, self.buf = self.buf[:total], self.buf[total:]
                    msgid, crc, serial = struct.unpack_from('<HIH', frame, 4)
                    body = frame[12:]
                    if zlib.crc32(body) & 0xffffffff != crc:
                        raise ValueError('Invalid frame CRC')
                    self.last_peer_serial = serial
                    try:
                        self.handle(msgid, body)
                    except ValueError as e:
                        legacy.log(f'[opening] rejected request {msgid}: {e}')
        except (OSError, ValueError) as e:
            legacy.log(f'[opening] connection closed: {e}')
        finally:
            self.closed = True
            self.conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=9003)
    parser.add_argument('--profile', type=Path, default=Path(__file__).parent / 'profiles/opening.json')
    args = parser.parse_args()
    store = OpeningStore(args.profile)
    legacy.LOG = str(Path(__file__).parent / 'logs/opening_server.log')
    current = None
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((args.host, args.port))
        listener.listen(4)
        legacy.log(f'[opening] listening {args.host}:{args.port} profile={args.profile}')
        while True:
            conn, addr = listener.accept()
            if current and not current.closed:
                current.closed = True
                try:
                    current.conn.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            current = OpeningClient(conn, addr, store)
            current.start()


if __name__ == '__main__':
    main()
