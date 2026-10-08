"""Regression coverage for opening save isolation and battle lifecycle."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from opening_state import OpeningStore


class OpeningStateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / 'opening.json'
        self.store = OpeningStore(self.path)

    def tearDown(self):
        self.directory.cleanup()

    def test_new_profile_does_not_skip_content(self):
        d = self.store.snapshot()
        self.assertEqual((d['level'], d['stamina']), (1, 90))
        self.assertEqual(d['last_normal_region'], 0)
        self.assertFalse(d['novice_completed'])
        self.assertEqual(d['vars'], {})
        self.assertEqual(d['heroes'], {})

    def test_both_character_choices_have_only_selected_hero(self):
        for selection in (0, 1):
            with self.subTest(selection=selection):
                store = OpeningStore(self.path.with_name(f'choice{selection}.json'))
                d = store.create_role('Start', selection)
                self.assertEqual(d['res_id'], 18 + selection)
                self.assertEqual(len(d['heroes']), 1)
                self.assertEqual(d['formations']['0'], ['', '', '', '', ''])
                self.assertEqual(next(iter(d['heroes'].values()))['level'], 1)

    def test_restart_preserves_vars_and_empty_formation_slots(self):
        self.store.create_role('Start', 0)
        self.store.set_var('NG_10011B', '1')
        self.store.save_formation(0, ['hero18', '', '', '', ''])
        reloaded = OpeningStore(self.path).snapshot()
        self.assertEqual(reloaded['vars']['NG_10011B'], '1')
        self.assertEqual(reloaded['formations']['0'], ['hero18', '', '', '', ''])

    def test_illegal_formation_rolls_back(self):
        self.store.create_role('Start', 0)
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            self.store.save_formation(0, ['hero18', 'unowned', '', '', ''])
        self.assertEqual(self.path.read_bytes(), before)

    def test_real_result_required_and_duplicate_settlement_is_idempotent(self):
        self.store.create_role('Start', 0)
        b = self.store.begin_battle(99)
        self.assertFalse(self.store.snapshot()['novice_completed'])
        self.assertTrue(self.store.settle_battle(b['id'], True))
        self.store.save_formation(0, ['hero18', '', '', '', ''])
        b = self.store.begin_battle(1001)
        self.assertTrue(self.store.settle_battle(b['id'], True, stars=3, coins=100, goods={'test': 1}))
        self.assertFalse(self.store.settle_battle(b['id'], True, stars=3, coins=100, goods={'test': 1}))
        d = self.store.snapshot()
        self.assertEqual((d['coins'], d['goods']['test']), (100, 1))
        self.assertEqual(d['last_normal_region'], 1001)
        self.assertEqual(d['region_stars']['10011'], 3)

    def test_story_entry_checks_progress_and_deducts_stamina_once(self):
        self.store.create_role('Start', 1)
        with self.assertRaises(ValueError):
            self.store.begin_battle(1001)
        b = self.store.begin_battle(99)
        self.store.settle_battle(b['id'], True)
        with self.assertRaises(ValueError):
            self.store.begin_battle(1002)
        with self.assertRaises(ValueError):
            self.store.begin_battle(1001)
        self.store.save_formation(0, ['hero19', '', '', '', ''])
        first = self.store.begin_battle(1001)
        second = self.store.begin_battle(1001)
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(self.store.snapshot()['stamina'], 82)

    def test_defeat_charges_configured_one_stamina(self):
        self.store.create_role('Start', 0)
        b = self.store.begin_battle(99)
        self.store.settle_battle(b['id'], True)
        self.store.save_formation(0, ['hero18', '', '', '', ''])
        b = self.store.begin_battle(1001)
        self.store.settle_battle(b['id'], False)
        self.assertEqual(self.store.snapshot()['stamina'], 89)
        self.assertEqual(self.store.snapshot()['last_normal_region'], 0)

    def test_failed_atomic_replace_preserves_old_save_and_memory(self):
        self.store.create_role('Start', 0)
        before = self.path.read_bytes()
        snapshot = self.store.snapshot()
        import os
        real_replace = os.replace
        def fail_save(src, dest):
            if Path(dest) == self.path:
                raise OSError('simulated interrupted save')
            return real_replace(src, dest)
        with patch('opening_state.os.replace', side_effect=fail_save):
            with self.assertRaises(OSError):
                self.store.set_var('NG_10011B', '1')
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.store.snapshot(), snapshot)
        self.assertEqual(self.path.with_suffix('.json.bak').read_bytes(), before)

    def test_opening_progression_recruitment_quest_and_advancement(self):
        from opening_data import PLAYER_LEVELS, HERO_LEVELS, rewards
        self.store.create_role('Start', 0)
        b = self.store.begin_battle(99)
        self.store.settle_battle(b['id'], True)
        self.store.save_formation(0, ['hero18', '', '', '', ''])
        for region in (1001, 1002, 1003):
            b = self.store.begin_battle(region)
            award = rewards(region, 1, True)
            self.store.settle_battle(b['id'], True, stars=3, **award,
                                    player_levels=PLAYER_LEVELS, hero_levels=HERO_LEVELS)
            if region == 1001:
                d = self.store.snapshot()
                self.assertEqual((d['level'], d['xp'], d['heroes']['hero18']['level']), (2, 2, 2))
                self.store.recruit('silver')
                self.store.set_var('NG_10011E', '1')
                self.assertNotIn('NG_10011E', OpeningStore(self.path).snapshot()['vars'])
                self.store.recruit('gold')
                self.assertEqual(self.store.snapshot()['vars']['NG_10011E'], '1')
                before = self.store.snapshot()
                _, is_new = self.store.recruit('gold')
                self.assertFalse(is_new)
                self.assertEqual(self.store.snapshot(), before)
                self.store.save_formation(0, ['hero18', 'hero31', '', '', ''])
        d = self.store.snapshot()
        self.assertEqual((d['level'], d['xp']), (3, 6))
        self.assertEqual((d['heroes']['hero18']['level'], d['heroes']['hero18']['xp']), (3, 20))
        self.assertEqual((d['heroes']['hero31']['level'], d['heroes']['hero31']['xp']), (2, 38))
        self.assertNotIn(1, d['claimed_quests'])
        d, is_new = self.store.claim_quest(1)
        self.assertTrue(is_new)
        self.assertEqual((d['coins'], d['gems']), (1199, 10))
        before = self.store.snapshot()
        self.assertFalse(self.store.claim_quest(1)[1])
        self.assertEqual(self.store.snapshot(), before)
        for slot in (1, 2, 3, 4):
            self.store.advance_slot('hero18', slot)
        self.store.set_var('NG_10031E', '1')
        self.assertNotIn('NG_10031E', OpeningStore(self.path).snapshot()['vars'])
        d = self.store.advance_hero('hero18')
        self.assertEqual(d['vars']['NG_10031E'], '1')
        self.assertEqual((d['coins'], d['heroes']['hero18']['stage']), (949, 1))
        self.assertEqual(d['heroes']['hero18']['params'], [0, 0, 0, 0])
        self.assertEqual(OpeningStore(self.path).snapshot(), d)

    def test_corruption_does_not_silently_create_a_new_character(self):
        self.path.write_text('{invalid', encoding='utf-8')
        with self.assertRaises(json.JSONDecodeError):
            OpeningStore(self.path)


if __name__ == '__main__':
    unittest.main()
