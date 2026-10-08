"""Opening protobuf regression tests against the original generated client serializers.

These tests decode independently of opening_wire.fields/proto and inspect serialized
public builder output. They do not load a DLL or require third-party packages.
Evidence: protobuf_serializer.dll Write RVAs 0x49724 (player), 0x5826c
(hero), 0x59c48 (once task), 0x43a18 (FBInfo), 0x30e00 (goods),
0x42eb8 (player attribute), 0x43644 (hero attribute), 0x50658 (vars).
"""
from datetime import datetime as RealDatetime
import unittest
from unittest.mock import patch

import opening_wire as wire
from opening_state import new_profile


def decode_fields(body):
    """Independent minimal protobuf reader: preserve tags, wires, repeats and zeroes."""
    data = bytes(body)
    offset = 0

    def integer():
        nonlocal offset
        value = 0
        for shift in range(0, 70, 7):
            if offset >= len(data):
                raise ValueError('truncated varint')
            byte = data[offset]
            offset += 1
            value |= (byte & 0x7f) << shift
            if byte < 0x80:
                return value
        raise ValueError('overlong varint')

    result = []
    while offset < len(data):
        key = integer()
        tag, kind = key >> 3, key & 7
        if tag == 0:
            raise ValueError('invalid field zero')
        if kind == 0:
            value = integer()
        elif kind in (1, 2, 5):
            size = integer() if kind == 2 else (8 if kind == 1 else 4)
            if size > len(data) - offset:
                raise ValueError('truncated field')
            value = data[offset:offset + size]
            offset += size
        else:
            raise ValueError(f'unsupported wire type {kind}')
        result.append((tag, kind, value))
    return result


def one_field(test, body, tag, kind):
    matches = [(w, v) for n, w, v in decode_fields(body) if n == tag]
    test.assertEqual(len(matches), 1, f'field {tag} must occur exactly once')
    actual_kind, value = matches[0]
    test.assertEqual(actual_kind, kind, f'field {tag}: wrong protobuf wire')
    return value


def repeated_fields(test, body, tag, kind):
    matches = [(w, v) for n, w, v in decode_fields(body) if n == tag]
    test.assertTrue(all(w == kind for w, v in matches), f'field {tag}: wrong repeated wire')
    return [v for w, v in matches]


def sample_hero(index=18, guid='hero18'):
    return {
        'guid': guid, 'index': index, 'level': 7, 'stage': 3,
        'xp': 130, 'stars': 2,
        # Distinct values catch the legacy rotated semantic mapping.
        'skills': {'MJ': 4, 'A': 5, 'B': 6, 'BD': 7},
    }


def sample_profile():
    data = new_profile()
    data.update({
        'account': 'fixture-account', 'role_name': '勇者', 'res_id': 19,
        'created_at': '2020-01-01 00:00:00',
        'level': 7, 'xp': 130, 'stamina': 82, 'gems': 265, 'coins': 1000,
        'last_normal_region': 1002, 'last_elite_region': 1001,
        'heroes': {'hero19': sample_hero(19, 'hero19')},
        'goods': {'GOODS104': 130, 'GOODS48': 0},
        'vars': {'NG_10011B': '1', 'MCPlay': '6', '剧情': '已完成'},
        'region_stars': {'10011': 3, '10021': 2, '10012': 1},
    })
    return data


class OpeningWireTests(unittest.TestCase):
    def test_task_fields_are_varints_and_zero_values_are_explicit(self):
        # COnceTaskInfo Write0x59c48: taskId1 / finishTimes2 / delete3 = wire0.
        body = wire.tasks([(1, 0, False), (130, 300, True)])
        self.assertEqual(body, bytes.fromhex(
            '0a06080110001800 0a0808820110ac021801'))
        entries = repeated_fields(self, body, 1, 2)
        self.assertEqual(decode_fields(entries[0]), [(1, 0, 1), (2, 0, 0), (3, 0, 0)])
        self.assertEqual(decode_fields(entries[1]), [(1, 0, 130), (2, 0, 300), (3, 0, 1)])

    def test_formation_preserves_five_slots_and_explicit_zero_type(self):
        # CMsgFormation: type1 wire0; five separate un-packed string positions2.
        slots = ['hero18', '', '', '', '']
        body = wire.formation(0, slots)
        self.assertEqual(body, bytes.fromhex(
            '0800 12066865726f3138 1200 1200 1200 1200'))
        self.assertEqual(one_field(self, body, 1, 0), 0)
        self.assertEqual(repeated_fields(self, body, 2, 2),
                         [b'hero18', b'', b'', b'', b''])
        body = wire.formation(15, ['', 'hero31', '', 'hero18', ''])
        self.assertEqual(one_field(self, body, 1, 0), 15)
        self.assertEqual(repeated_fields(self, body, 2, 2),
                         [b'', b'hero31', b'', b'hero18', b''])

    def test_hero_scalar_fields_and_mj_a_b_bd_skill_order(self):
        # Generated Write0x5826c supplies tags; original GenerateWj0x351ec
        # maps Skillindex1=MJ, 2=A, 3=B, 4=BD. All levels use varint.
        body = wire.hero(sample_hero())
        self.assertEqual(one_field(self, body, 1, 2), b'hero18')
        expected = {2: 18, 3: 7, 4: 3, 5: 130, 6: 2,
                    11: 4, 12: 5, 13: 6, 14: 7}
        for tag, value in expected.items():
            with self.subTest(tag=tag):
                self.assertEqual(one_field(self, body, tag, 0), value)

    def test_hero_stage_parameters_are_distinct_varint_fields(self):
        hero = sample_hero()
        hero['params'] = [1, 2, 130, 300]
        body = wire.hero(hero)
        for tag, value in zip(range(7, 11), hero['params']):
            with self.subTest(tag=tag):
                self.assertEqual(one_field(self, body, tag, 0), value)

    def test_player_snapshot_scalar_tags_and_countdown_use_varints(self):
        # Player Write0x49724; default/zero values remain legal explicit wire0.
        body = wire.player(sample_profile(), account='transport-account')
        expected = {1: 1, 3: 7, 5: 130, 6: 82, 7: 265, 8: 1000,
                    9: 1002, 10: 1001, 11: 10, 12: 20, 35: 2, 36: 0}
        for tag, value in expected.items():
            with self.subTest(tag=tag):
                self.assertEqual(one_field(self, body, tag, 0), value)
        self.assertEqual(one_field(self, body, 2, 2), b'transport-account')
        self.assertEqual(one_field(self, body, 48, 2), b'2020-01-01 00:00:00')

    def test_fresh_snapshot_is_not_an_active_challenge_resume(self):
        # BOBChallengeInfo.set_BOBIsForceExit0x866c4 interprets default round0
        # as an unfinished challenge. Idle boundary is round1 (also reset path0x274d44).
        body = wire.player(sample_profile())
        self.assertEqual(one_field(self, body, 22, 0), 1)
        self.assertEqual(one_field(self, body, 23, 0), 0)

    def test_next_day_countdown_is_integer_seconds_to_midnight(self):
        class FrozenDatetime(RealDatetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2024, 1, 1, 23, 0, 0)
        data = sample_profile()
        data['created_at'] = '2024-01-01 15:00:00'
        with patch.object(wire, 'datetime', FrozenDatetime):
            body = wire.player(data)
        self.assertEqual(one_field(self, body, 36, 0), 3600)

    def test_snapshot_heroes_goods_and_player_vars_use_correct_nested_tags(self):
        body = wire.player(sample_profile())
        heroes = repeated_fields(self, body, 101, 2)
        self.assertEqual(len(heroes), 1)
        self.assertEqual(one_field(self, heroes[0], 1, 2), b'hero19')
        self.assertEqual(one_field(self, heroes[0], 2, 0), 19)
        goods = {
            one_field(self, item, 1, 2).decode('utf-8'): one_field(self, item, 2, 0)
            for item in repeated_fields(self, body, 102, 2)
        }
        self.assertEqual(goods, {'GOODS104': 130, 'GOODS48': 0})
        variables = {
            one_field(self, item, 1, 2).decode('utf-8'):
                one_field(self, item, 2, 2).decode('utf-8')
            for item in repeated_fields(self, body, 109, 2)
        }
        self.assertEqual(variables, {'NG_10011B': '1', 'MCPlay': '6', '剧情': '已完成'})

    def test_snapshot_fb_stars_use_tag_103_not_equipment_tag_106(self):
        # get_FBStar at IL0x485b9, header103 at0x485de / Write0x49724.
        body = wire.player(sample_profile())
        stars = {
            one_field(self, entry, 1, 0): one_field(self, entry, 2, 0)
            for entry in repeated_fields(self, body, 103, 2)
        }
        self.assertEqual(stars, {10011: 3, 10021: 2, 10012: 1})
        self.assertEqual(repeated_fields(self, body, 106, 2), [])

    def test_snapshot_free_draw_dates_are_tags_30_31_and_count_32(self):
        # Generated player Write0x49724, not standalone cooldown update2402.
        data = sample_profile()
        data['draws'].update({'silver': 2, 'gold': 1,
                             'silver_time': '2020-01-02 03:04:05',
                             'gold_time': '2020-01-03 06:07:08'})
        body = wire.player(data)
        self.assertEqual(one_field(self, body, 30, 2), b'2020-01-02 03:04:05')
        self.assertEqual(one_field(self, body, 31, 2), b'2020-01-03 06:07:08')
        self.assertEqual(one_field(self, body, 32, 0), 3)

    def test_snapshot_resource_data_has_all_client_required_types(self):
        body = wire.player(sample_profile())
        entries = repeated_fields(self, body, 115, 2)
        self.assertEqual({one_field(self, item, 1, 0) for item in entries}, {5, 6, 8, 9, 10})
        for entry in entries:
            # Omitted playTime2 means protobuf default zero.
            values = {n: (w, v) for n, w, v in decode_fields(entry)}
            self.assertEqual(values.get(2, (0, 0)), (0, 0))
            timestamp = one_field(self, entry, 3, 2).decode('utf-8')
            RealDatetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')

    def test_main_player_wraps_snapshot_in_tag4(self):
        data = sample_profile()
        body = wire.main_player(data, account='transport-account')
        self.assertEqual(one_field(self, body, 1, 0), 1)
        self.assertEqual(one_field(self, body, 2, 0), 19)
        self.assertEqual(one_field(self, body, 3, 2).decode('utf-8'), '勇者')
        player = one_field(self, body, 4, 2)
        self.assertEqual(one_field(self, player, 2, 2), b'transport-account')
        self.assertEqual(one_field(self, player, 35, 0), 2)

    def test_enter_selects_novice_flag_and_selected_role_index(self):
        data = sample_profile()
        for completed in (False, True):
            with self.subTest(completed=completed):
                data['novice_completed'] = completed
                body = wire.enter(data)
                self.assertEqual(one_field(self, body, 1, 0), 1)
                self.assertEqual(one_field(self, body, 2, 0), int(completed))
                self.assertEqual(one_field(self, body, 4, 0), 2)
                timestamp = one_field(self, body, 5, 2).decode('utf-8')
                RealDatetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')

    def test_player_attribute_501_is_kind_and_absolute_varint_value(self):
        # CCSMsgAttriUpdate Write0x42eb8: type1 wire0, iValue2 wire0.
        self.assertEqual(wire.player_attribute(3, 1000), bytes.fromhex('080310e807'))
        self.assertEqual(wire.player_attribute(4, 0), bytes.fromhex('08041000'))
        self.assertEqual(decode_fields(wire.player_attribute(6, 2)), [(1, 0, 6), (2, 0, 2)])

    def test_goods_update_301_count_is_varint_including_zero_total(self):
        # CCMsgShiningAwardItem Write0x30e00, not fixed32 count.
        self.assertEqual(wire.goods('GOODS104', 130), bytes.fromhex(
            '0a08474f4f4453313034 108201'))
        self.assertEqual(wire.goods('GOODS48', 0), bytes.fromhex(
            '0a07474f4f44533438 1000'))
        self.assertEqual(one_field(self, wire.goods('GOODS104', 130), 2, 0), 130)

    def test_fb_info_401_matches_configured_rewards_without_duplicate_fixed_goods(self):
        # CCSMsgFBInfo Write0x43a18. Config-fixed drops are added by client
        # independently; excluding awards.goods here avoids duplicate item drops.
        awards = {'coins': 55, 'xp': 8, 'hero_xp': 32,
                  'goods': {'GOODS42': 1, 'GOODS104': 2}}
        body = wire.fb_info(1001, awards)
        self.assertEqual(body, bytes.fromhex('08e9071037180820204000'))
        self.assertEqual(decode_fields(body),
                         [(1, 0, 1001), (2, 0, 55), (3, 0, 8), (4, 0, 32), (8, 0, 0)])
        self.assertEqual(repeated_fields(self, body, 7, 2), [])

    def test_fb_info_zero_rewards_still_has_region_and_false_need_check(self):
        body = wire.fb_info(1003, {'coins': 0, 'xp': 0, 'hero_xp': 0, 'goods': {}})
        self.assertEqual(body, bytes.fromhex('08eb074000'))
        self.assertEqual(one_field(self, body, 8, 0), 0)

    def test_hero_attribute_601_guid_kind_and_value_have_correct_wire_types(self):
        # CCSMsgWuJiangAttriUpdate Write0x43644.
        body = wire.hero_attribute('hero18', 1, 130)
        self.assertEqual(body, bytes.fromhex('0a066865726f31381001188201'))
        self.assertEqual(decode_fields(body), [(1, 2, b'hero18'), (2, 0, 1), (3, 0, 130)])
        self.assertEqual(one_field(self, wire.hero_attribute('hero18', 1, 0), 3, 0), 0)

    def test_gold_draw_2401_reports_single_guaranteed_hero31(self):
        # DrawRet Write0x24ca8 / award Write0xab78 / role Write0xada0.
        body = wire.draw_result('gold')
        self.assertEqual(body, bytes.fromhex('080210011a0608021a02081f'))
        self.assertEqual(one_field(self, body, 1, 0), 2)
        self.assertEqual(one_field(self, body, 2, 0), 1)
        awards = repeated_fields(self, body, 3, 2)
        self.assertEqual(len(awards), 1)
        self.assertEqual(one_field(self, awards[0], 1, 0), 2)
        role = one_field(self, awards[0], 3, 2)
        self.assertEqual(one_field(self, role, 1, 0), 31)

    def test_silver_draw_2401_reports_single_goods48_item(self):
        body = wire.draw_result('silver')
        self.assertEqual(body, bytes.fromhex(
            '080110011a0f0803220b0a07474f4f445334381001'))
        self.assertEqual(one_field(self, body, 1, 0), 1)
        self.assertEqual(one_field(self, body, 2, 0), 1)
        awards = repeated_fields(self, body, 3, 2)
        self.assertEqual(len(awards), 1)
        self.assertEqual(one_field(self, awards[0], 1, 0), 3)
        item = one_field(self, awards[0], 4, 2)
        self.assertEqual(decode_fields(item), [(1, 2, b'GOODS48'), (2, 0, 1)])

    def test_draw_counters_2402_dates_and_counts_are_not_player_snapshot_tags(self):
        data = sample_profile()
        data['draws'].update({'silver': 2, 'gold': 1,
                             'silver_time': '2020-01-02 03:04:05',
                             'gold_time': '2020-01-03 06:07:08'})
        body = wire.draw_counters(data)
        self.assertEqual(decode_fields(body), [
            (1, 2, b'2020-01-02 03:04:05'), (2, 2, b'2020-01-03 06:07:08'),
            (3, 0, 3), (4, 0, 0),
        ])

    def test_empty_arena_2001_has_varint_zero_scalars_and_present_target_wrapper(self):
        # JJCInfo.UpdateData requires targets6 wrapper even with no opponents.
        # Scalars1..4 are ordinary int32 wire0, not the legacy fixed32 guess.
        body = wire.empty_arena_info()
        self.assertEqual(body, bytes.fromhex('08001000180020003200'))
        self.assertEqual(decode_fields(body), [
            (1, 0, 0), (2, 0, 0), (3, 0, 0), (4, 0, 0), (6, 2, b''),
        ])
        self.assertEqual(decode_fields(one_field(self, body, 6, 2)), [])


if __name__ == '__main__':
    unittest.main()
