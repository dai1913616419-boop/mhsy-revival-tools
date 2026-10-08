"""Offline story-handler regressions using coalesced, CRC-checked protocol frames.

Only this file is owned by this task. The socket/log boundaries are fixtures;
OpeningClient.run/handle and OpeningStore persist real temporary profiles. Expected
costs/rewards are literals read from bundled config, not production reward builders.
The fixture starts after novice completion via public OpeningStore lifecycle APIs.

Original BattleController0x161b4 and escort0x25ce0 send302 with result1=1 and
starCount2=max(1, 3-GetMemberDeadCount()). Both fields are varints (Write0x2e774).
Every successful stage fixture includes104(region) after301, matching scene readiness.
"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from opening_server import OpeningClient
from opening_state import OpeningStore
from test_opening_protocol import (
    MemorySocket, integer_field, request_frame, response_frames, string_field,
)
from test_opening_wire import decode_fields, one_field, repeated_fields


def entry(region):
    return integer_field(1, region) + integer_field(2, 1)


def win(stars):
    return integer_field(1, 1) + integer_field(2, stars)


def stage_messages(region, stars=3, return_city=True):
    messages = [(301, entry(region)), (104, integer_field(1, region)), (302, win(stars))]
    if return_city:
        messages.append((304, b''))
    return messages


def formation(slots):
    return integer_field(1, 0) + b''.join(string_field(2, slot) for slot in slots)


def starter_selection():
    # Real G1001_Begin click selects the owned starter into otherwise empty PVE slots.
    return (202, formation(['hero18', '', '', '', '']))


class OpeningStoryProtocolTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'story.json'
        self.store = OpeningStore(self.path)
        self.store.create_role('Story', 0)
        novice = self.store.begin_battle(99)
        self.store.settle_battle(novice['id'], True)
        log_patch = patch('opening_server.legacy.log')
        self.logs = log_patch.start()
        self.addCleanup(log_patch.stop)
        save_patch = patch('opening_server.legacy.write_save')
        self.legacy_write = save_patch.start()
        self.addCleanup(save_patch.stop)

    def exchange(self, messages, initialize=True, rejected=False, store=None):
        if initialize:
            messages = [(102, b''), (104, integer_field(1, 1))] + list(messages)
        data = b''.join(request_frame(msgid, body, serial)
                        for serial, (msgid, body) in enumerate(messages, 1))
        conn = MemorySocket([data])  # All requests arrive in one coalesced recv.
        client = OpeningClient(conn, ('offline-story-fixture', 0), store or self.store)
        before_logs = len(self.logs.call_args_list)
        client.run()
        frames = response_frames(conn.output)  # Independent length/CRC verification.
        self.assertTrue(client.closed)
        self.assertTrue(conn.closed)
        self.assertEqual(conn.recv_calls, 2)
        self.assertEqual([serial for mid, body, serial in frames], list(range(1, len(frames) + 1)))
        self.legacy_write.assert_not_called()
        failures = [str(call) for call in self.logs.call_args_list[before_logs:]
                    if 'rejected request' in str(call) or 'connection closed:' in str(call)]
        if rejected:
            self.assertTrue(failures, 'fixture must exercise an actual rejected handler request')
        else:
            self.assertEqual(failures, [], 'valid client fixture was unexpectedly rejected')
        return frames

    def bodies(self, frames, msgid):
        return [body for mid, body, serial in frames if mid == msgid]

    def only(self, frames, msgid):
        bodies = self.bodies(frames, msgid)
        self.assertEqual(len(bodies), 1, f'expected one response{msgid}')
        return bodies[0]

    def player_values(self, frames):
        return {one_field(self, body, 1, 0): one_field(self, body, 2, 0)
                for body in self.bodies(frames, 501)}

    def goods_values(self, frames):
        return {one_field(self, body, 1, 2).decode('utf-8'): one_field(self, body, 2, 0)
                for body in self.bodies(frames, 301)}

    def finish_stage(self, region, stars=3):
        messages = stage_messages(region, stars)
        if not self.store.snapshot()['formations']['0'][0]:
            messages.insert(0, starter_selection())
        # Never overwrite later guide formation [hero31, hero18, ...].
        return self.exchange(messages)

    def complete_stories(self, recruit=True):
        self.finish_stage(1001, 2)
        if recruit:
            self.exchange([(2201, bytes.fromhex('0801')), (2202, bytes.fromhex('0801')),
                           (202, formation(['hero31', 'hero18', '', '', '']))])
        self.finish_stage(1002, 1)
        self.finish_stage(1003, 2)

    def test_stage_entry_sends401_before107_and_duplicate_entry_costs_only_once(self):
        frames = self.exchange([starter_selection(), (301, entry(1001)), (301, entry(1001))])
        initial = one_field(self, self.only(frames, 102), 4, 2)
        self.assertEqual(one_field(self, initial, 22, 0), 1)
        self.assertEqual(one_field(self, initial, 23, 0), 0)
        owned = repeated_fields(self, initial, 101, 2)
        self.assertEqual(len(owned), 1)
        self.assertEqual(one_field(self, owned[0], 2, 0), 18)
        self.assertEqual(repeated_fields(self, self.only(frames, 201), 2, 2),
                         [b'', b'', b'', b'', b''])
        ids = [mid for mid, body, serial in frames]
        info_indices = [i for i, mid in enumerate(ids) if mid == 401]
        change_indices = [i for i, mid in enumerate(ids) if mid == 107]
        self.assertEqual(len(info_indices), 2)
        self.assertEqual(len(change_indices), 2)
        for info, change in zip(info_indices, change_indices):
            self.assertLess(info, change, 'FBInfo must be cached before scene construction')
            self.assertEqual(frames[info][1], bytes.fromhex('08e9071037180820204000'))
            self.assertEqual(frames[change][1], bytes.fromhex('08e907'))
            self.assertEqual(ids[change - 1], 103, 'born position must precede region response')
        self.assertEqual([one_field(self, body, 2, 0) for body in self.bodies(frames, 501)], [82, 82])
        saved = OpeningStore(self.path).snapshot()
        self.assertEqual(saved['stamina'], 82)
        self.assertEqual(saved['level'], 1)
        self.assertEqual(saved['coins'], 0)
        self.assertEqual(saved['goods'], {})
        self.assertEqual(saved['battle_sequence'], 2)
        self.assertEqual(saved['formations']['0'], ['hero18', '', '', '', ''])

    def test_first_win_retransmission_is_canonical_and_grants_only_once(self):
        frames = self.exchange([
            starter_selection(),
            (301, entry(1001)), (104, integer_field(1, 1001)),
            (302, bytes.fromhex('08011002')),  # One member died: two reported stars.
            (302, bytes.fromhex('08011001')),  # Contradictory retransmission.
            (302, bytes.fromhex('0802')),      # Must not turn a saved win into loss.
            (304, b''),
        ])
        self.assertEqual(self.bodies(frames, 1001), [bytes.fromhex('08011002')] * 3)
        self.assertEqual(self.player_values(frames), {2: 102, 6: 2, 1: 2, 3: 55, 4: 0})
        self.assertEqual(len(self.bodies(frames, 501)), 6, 'duplicates must not resend grants')
        self.assertEqual(self.goods_values(frames), {'GOODS42': 1, 'GOODS104': 2})
        self.assertEqual(len(self.bodies(frames, 301)), 2)
        self.assertEqual(self.bodies(frames, 1104), [])
        saved = OpeningStore(self.path).snapshot()
        self.assertEqual((saved['level'], saved['xp'], saved['stamina'], saved['coins']), (2, 2, 102, 55))
        self.assertEqual(saved['region_stars'], {'10011': 2})
        self.assertEqual(saved['goods'], {'GOODS42': 1, 'GOODS104': 2})
        self.assertEqual((saved['heroes']['hero18']['level'], saved['heroes']['hero18']['xp']), (2, 2))

    def test_reported_stars_are_preserved_and_repeat_clear_drops_are_not_regranted(self):
        first = self.finish_stage(1001, 1)
        self.assertEqual(self.only(first, 1001), bytes.fromhex('08011001'))
        self.assertEqual(self.store.snapshot()['region_stars'], {'10011': 1})
        second = self.finish_stage(1001, 2)
        self.assertEqual(self.only(second, 1001), bytes.fromhex('08011002'))
        self.assertEqual(self.store.snapshot()['region_stars'], {'10011': 2})
        self.assertEqual(self.bodies(second, 301), [], 'first-clear materials must not repeat')
        third = self.finish_stage(1001, 1)
        self.assertEqual(self.only(third, 1001), bytes.fromhex('08011001'))
        saved = OpeningStore(self.path).snapshot()
        self.assertEqual(saved['region_stars'], {'10011': 2}, 'best stars cannot decrease')
        self.assertEqual(saved['goods'], {'GOODS42': 1, 'GOODS104': 2})
        self.assertEqual(saved['coins'], 165)
        self.assertEqual((saved['level'], saved['xp']), (3, 6))
        self.assertEqual(saved['last_normal_region'], 1001)
        self.assertEqual(saved['quest_progress'], {})

    def test_defeat_charges_one_stamina_and_conflicting_win_replay_has_no_reward(self):
        frames = self.exchange([
            starter_selection(),
            (301, entry(1001)), (104, integer_field(1, 1001)),
            (302, bytes.fromhex('0802')), (302, bytes.fromhex('08011002')), (304, b''),
        ])
        self.assertEqual(self.bodies(frames, 1001), [bytes.fromhex('08021000')] * 2)
        saved = OpeningStore(self.path).snapshot()
        self.assertEqual((saved['level'], saved['xp'], saved['coins'], saved['stamina']), (1, 0, 0, 89))
        self.assertEqual(saved['goods'], {})
        self.assertEqual(saved['region_stars'], {})
        self.assertEqual(saved['last_normal_region'], 0)
        self.assertEqual(saved['quest_progress'], {})
        self.assertEqual((saved['heroes']['hero18']['level'], saved['heroes']['hero18']['xp']), (1, 0))
        self.assertTrue(all(count == 0 for count in self.goods_values(frames).values()))

    def test_result_requires_scene_ready_and_actual_reported_win_stars(self):
        frames = self.exchange([
            starter_selection(),
            (301, entry(1001)),
            (302, bytes.fromhex('08011002')),  # Rejected:104(scene-ready) not received.
            (104, integer_field(1, 1002)),
            (302, bytes.fromhex('08011002')),  # Rejected: wrong ready scene for active1001.
            (104, integer_field(1, 1001)),
            (302, bytes.fromhex('0801')),      # Rejected: no starCount2.
            (302, bytes.fromhex('08011000')),  # Rejected: invalid zero win stars.
            (302, bytes.fromhex('08011004')),  # Rejected: above three.
            (302, bytes.fromhex('08031002')),  # Rejected: unknown outcome.
            (302, bytes.fromhex('08011002')), (304, b''),
        ], rejected=True)
        self.assertEqual(self.bodies(frames, 1001), [bytes.fromhex('08011002')])
        saved = OpeningStore(self.path).snapshot()
        self.assertEqual(saved['region_stars'], {'10011': 2})
        self.assertEqual((saved['coins'], saved['level'], saved['xp']), (55, 2, 2))
        self.assertEqual(saved['goods'], {'GOODS42': 1, 'GOODS104': 2})

    def test_recruitment_is_locked_before1001_and_adds_hero_before_gold_animation_once(self):
        before = self.store.snapshot()
        locked = self.exchange([(2201, bytes.fromhex('0801')), (2202, bytes.fromhex('0801'))],
                               rejected=True)
        self.assertEqual(self.bodies(locked, 1204), [])
        self.assertEqual(self.bodies(locked, 2401), [])
        self.assertEqual(self.store.snapshot(), before)
        self.finish_stage(1001, 2)
        frames = self.exchange([
            (2201, bytes.fromhex('0801')), (2201, bytes.fromhex('0801')),
            (2202, bytes.fromhex('0801')), (2202, bytes.fromhex('0801')),
        ])
        additions = [(i, body) for i, (mid, body, serial) in enumerate(frames) if mid == 1204]
        self.assertEqual(len(additions), 1, 'replayed gold draw must not duplicate ownership')
        hero = one_field(self, additions[0][1], 1, 2)
        self.assertEqual(one_field(self, hero, 1, 2), b'hero31')
        self.assertEqual(one_field(self, hero, 2, 0), 31)
        self.assertEqual(one_field(self, hero, 3, 0), 1)
        self.assertEqual(one_field(self, additions[0][1], 2, 0), 0)
        gold = [(i, body) for i, (mid, body, serial) in enumerate(frames)
                if mid == 2401 and one_field(self, body, 1, 0) == 2]
        self.assertEqual(len(gold), 2)
        self.assertLess(additions[0][0], gold[0][0], 'UI resolves hero ownership before2401')
        self.assertEqual([body for i, body in gold], [bytes.fromhex('080210011a0608021a02081f')] * 2)
        self.assertEqual(self.goods_values(frames), {'GOODS48': 1})
        saved = OpeningStore(self.path).snapshot()
        self.assertEqual(set(saved['heroes']), {'hero18', 'hero31'})
        self.assertEqual(saved['goods'], {'GOODS42': 1, 'GOODS104': 2, 'GOODS48': 1})
        self.assertEqual((saved['draws']['silver'], saved['draws']['gold']), (1, 1))
        self.assertEqual(saved['coins'], 55, 'guided first draws must remain free/idempotent')
        counters = self.bodies(frames, 2402)
        self.assertEqual(len(counters), 4)
        self.assertEqual(one_field(self, counters[-1], 3, 0), 4)

    def test_quest_claim_before1003_is_rejected_without_grant(self):
        self.finish_stage(1001, 2)
        self.finish_stage(1002, 1)
        before = self.store.snapshot()
        frames = self.exchange([(704, bytes.fromhex('0801'))], rejected=True)
        self.assertEqual(self.store.snapshot(), before)
        self.assertEqual(self.bodies(frames, 501), [])
        self.assertEqual(self.bodies(frames, 301), [])
        self.assertEqual(self.bodies(frames, 1104), [])
        self.assertEqual(before['claimed_quests'], [])
        self.assertEqual(before['quest_progress'], {})

    def test_1003_completes_but_does_not_claim_quest_or_reward_duplicate_results(self):
        self.finish_stage(1001, 2)
        self.exchange([(2201, bytes.fromhex('0801')), (2202, bytes.fromhex('0801')),
                       (202, formation(['hero31', 'hero18', '', '', '']))])
        self.finish_stage(1002, 1)
        frames = self.finish_stage(1003, 2)
        self.assertEqual(self.only(frames, 1104), bytes.fromhex('0a06080110011800'))
        before = OpeningStore(self.path).snapshot()
        self.assertEqual((before['coins'], before['gems'], before['goods']['GOODS104']), (199, 0, 6))
        self.assertEqual(before['claimed_quests'], [])
        self.assertEqual(before['quest_progress'], {'1': 1})
        self.assertEqual((before['level'], before['xp'], before['stamina']), (3, 6, 106))
        self.assertEqual((before['heroes']['hero18']['level'], before['heroes']['hero18']['xp']), (3, 20))
        self.assertEqual((before['heroes']['hero31']['level'], before['heroes']['hero31']['xp']), (2, 38))
        duplicate = self.exchange([(302, bytes.fromhex('08011002')), (302, bytes.fromhex('0802'))])
        self.assertEqual(self.store.snapshot(), before)
        self.assertEqual(self.bodies(duplicate, 1001), [bytes.fromhex('08011002')] * 2)
        for msgid in (501, 601, 301, 1104):
            self.assertEqual(self.bodies(duplicate, msgid), [], f'duplicate must not repeat update{msgid}')

    def test_704_claim_is_atomic_once_only_and_claimed_task_stays_removed(self):
        self.complete_stories()
        before = self.store.snapshot()
        frames = self.exchange([(704, bytes.fromhex('0801')), (704, bytes.fromhex('0801')), (703, b'')])
        self.assertEqual(self.player_values(frames), {3: 1199, 4: 10})
        self.assertEqual(len(self.bodies(frames, 501)), 2)
        self.assertEqual(self.goods_values(frames), {'GOODS104': 7})
        self.assertEqual(len(self.bodies(frames, 301)), 1)
        self.assertEqual(self.bodies(frames, 1104), [bytes.fromhex('0a06080110011801')] * 2)
        self.assertEqual(repeated_fields(self, self.only(frames, 1103), 1, 2), [])
        saved = OpeningStore(self.path).snapshot()
        self.assertEqual(saved['claimed_quests'], [1])
        self.assertEqual((saved['coins'], saved['gems'], saved['goods']['GOODS104']), (1199, 10, 7))
        self.assertEqual((saved['level'], saved['xp'], saved['stamina']),
                         (before['level'], before['xp'], before['stamina']))
        reload_frames = self.exchange([(703, b'')], store=OpeningStore(self.path))
        self.assertEqual(repeated_fields(self, self.only(reload_frames, 1103), 1, 2), [])

    def test_advancement_rejects_missing_material_and_premature_promotion(self):
        self.finish_stage(1001, 2)  # Starter lv2, GOODS42 only, no GOODS51 yet.
        before = self.store.snapshot()
        frames = self.exchange([
            (904, string_field(1, 'hero18') + integer_field(2, 2)),
            (905, string_field(1, 'hero18')),
        ], rejected=True)
        self.assertEqual(self.store.snapshot(), before)
        for msgid in (501, 601, 301):
            self.assertEqual(self.bodies(frames, msgid), [])
        self.assertEqual(before['heroes']['hero18']['params'], [0, 0, 0, 0])
        self.assertEqual(before['heroes']['hero18']['stage'], 0)

    def test_904_consumes_each_material_once_and_905_promotes_for250_once(self):
        self.complete_stories()
        self.exchange([(704, bytes.fromhex('0801'))])
        frames = self.exchange([
            (904, string_field(1, 'hero18') + integer_field(2, 1)),
            (904, string_field(1, 'hero18') + integer_field(2, 1)),
            (904, string_field(1, 'hero18') + integer_field(2, 2)),
            (904, string_field(1, 'hero18') + integer_field(2, 3)),
            (904, string_field(1, 'hero18') + integer_field(2, 4)),
            (905, string_field(1, 'hero18')), (905, string_field(1, 'hero18')),
        ])
        goods = [(one_field(self, body, 1, 2).decode('utf-8'), one_field(self, body, 2, 0))
                 for body in self.bodies(frames, 301)]
        self.assertEqual(goods, [('GOODS42', 0), ('GOODS42', 0),
                                 ('GOODS51', 1), ('GOODS51', 0), ('GOODS48', 1)])
        hero_updates = [(one_field(self, body, 1, 2).decode('utf-8'),
                         one_field(self, body, 2, 0), one_field(self, body, 3, 0))
                        for body in self.bodies(frames, 601)]
        self.assertEqual(hero_updates, [
            ('hero18', 5, 1), ('hero18', 5, 1), ('hero18', 6, 1),
            ('hero18', 7, 1), ('hero18', 8, 1), ('hero18', 3, 1), ('hero18', 3, 1),
        ])
        self.assertEqual(self.player_values(frames), {3: 949})
        self.assertEqual([one_field(self, body, 2, 0) for body in self.bodies(frames, 501)], [949, 949])
        saved = OpeningStore(self.path).snapshot()
        self.assertEqual((saved['coins'], saved['gems']), (949, 10))
        self.assertEqual(saved['goods'], {'GOODS42': 0, 'GOODS104': 7, 'GOODS48': 1, 'GOODS51': 0})
        self.assertEqual(saved['heroes']['hero18']['stage'], 1)
        self.assertEqual(saved['heroes']['hero18']['params'], [0, 0, 0, 0])
        self.assertEqual(saved['heroes']['hero31']['stage'], 0)

    def test_full_reload_restores_progress_roster_materials_vars_and_claim_without_regrant(self):
        self.complete_stories()
        self.exchange([(704, bytes.fromhex('0801'))] + [
            (904, string_field(1, 'hero18') + integer_field(2, slot)) for slot in (1, 2, 3, 4)
        ] + [
            (905, string_field(1, 'hero18')),
            (1801, string_field(1, 'NG_10031E') + string_field(2, '1')),
            (1801, string_field(1, 'MCPlay') + string_field(2, '6')),
        ])
        before = self.store.snapshot()
        reloaded = OpeningStore(self.path)
        self.assertEqual(reloaded.snapshot(), before)
        frames = self.exchange([(601, b''), (703, b'')], initialize=False, store=reloaded)
        player = one_field(self, self.only(frames, 901), 2, 2)
        for tag, value in {3: 3, 5: 6, 6: 106, 7: 10, 8: 949, 9: 1003, 10: 0,
                           22: 1, 23: 0, 35: 1}.items():
            with self.subTest(tag=tag):
                self.assertEqual(one_field(self, player, tag, 0), value)
        stars = {one_field(self, body, 1, 0): one_field(self, body, 2, 0)
                 for body in repeated_fields(self, player, 103, 2)}
        self.assertEqual(stars, {10011: 2, 10021: 1, 10031: 2})
        owned = {one_field(self, body, 1, 2).decode('utf-8'): body
                 for body in repeated_fields(self, player, 101, 2)}
        self.assertEqual(set(owned), {'hero18', 'hero31'})
        for tag, value in {2: 18, 3: 3, 4: 1, 5: 20, 6: 1, 7: 0, 8: 0, 9: 0, 10: 0}.items():
            self.assertEqual(one_field(self, owned['hero18'], tag, 0), value)
        for tag, value in {2: 31, 3: 2, 4: 0, 5: 38, 6: 1}.items():
            self.assertEqual(one_field(self, owned['hero31'], tag, 0), value)
        goods = {one_field(self, body, 1, 2).decode('utf-8'): one_field(self, body, 2, 0)
                 for body in repeated_fields(self, player, 102, 2)}
        self.assertEqual(goods, {'GOODS42': 0, 'GOODS104': 7, 'GOODS48': 1, 'GOODS51': 0})
        variables = {one_field(self, body, 1, 2).decode('utf-8'):
                         one_field(self, body, 2, 2).decode('utf-8')
                     for body in repeated_fields(self, player, 109, 2)}
        self.assertEqual(variables, {'NG_10031E': '1', 'MCPlay': '6'})
        self.assertEqual(repeated_fields(self, self.only(frames, 201), 2, 2),
                         [b'hero31', b'hero18', b'', b'', b''])
        self.assertEqual(one_field(self, player, 30, 2).decode('utf-8'), before['draws']['silver_time'])
        self.assertEqual(one_field(self, player, 31, 2).decode('utf-8'), before['draws']['gold_time'])
        self.assertEqual(one_field(self, player, 32, 0), 4)
        self.assertEqual(repeated_fields(self, self.only(frames, 1103), 1, 2), [])
        for msgid in (1204, 2401, 501, 601, 301, 1104):
            self.assertEqual(self.bodies(frames, msgid), [], f'reload must not regrant/update{msgid}')
        self.assertEqual(reloaded.snapshot(), before)

    def test_empty_permanent_formation_blocks_story_without_losing_owned_starter(self):
        before = self.store.snapshot()
        self.assertEqual(before['formations']['0'], ['', '', '', '', ''])
        self.assertEqual(set(before['heroes']), {'hero18'})
        frames = self.exchange([(301, entry(1001))], rejected=True)
        self.assertEqual(self.store.snapshot(), before, 'rejected entry cannot charge VP or start battle')
        for msgid in (401, 107, 501):
            self.assertEqual(self.bodies(frames, msgid), [])
        self.assertEqual(repeated_fields(self, self.only(frames, 201), 2, 2),
                         [b'', b'', b'', b'', b''])
        player = one_field(self, self.only(frames, 102), 4, 2)
        owned = repeated_fields(self, player, 101, 2)
        self.assertEqual(len(owned), 1)
        self.assertEqual(one_field(self, owned[0], 2, 0), 18)


if __name__ == '__main__':
    unittest.main()
