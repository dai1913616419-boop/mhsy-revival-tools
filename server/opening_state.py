"""Persistent single-player opening profiles, separate from the legacy demo save."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
import threading

SCHEMA_VERSION = 1
STORY_REGIONS = (1001, 1002, 1003)


def new_profile() -> dict:
    return {
        'schema_version': SCHEMA_VERSION,
        'account': 'local', 'role_name': '', 'res_id': 18,
        'level': 1, 'xp': 0, 'stamina': 90, 'coins': 0, 'gems': 0,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'novice_completed': False,
        'last_normal_region': 0, 'last_elite_region': 0,
        'region_stars': {}, 'heroes': {}, 'goods': {}, 'formations': {},
        'vars': {}, 'pending_vars': {}, 'quest_progress': {}, 'claimed_quests': [],
        'draws': {'silver': 0, 'gold': 0},
        'battle': None, 'battle_sequence': 0, 'settled_battles': [],
    }


def validate_profile(data: dict) -> None:
    if not isinstance(data, dict) or data.get('schema_version') != SCHEMA_VERSION:
        raise ValueError('Unsupported or malformed opening profile')
    for key in ('level', 'xp', 'stamina', 'coins', 'gems', 'battle_sequence'):
        if type(data.get(key)) is not int or data[key] < (1 if key == 'level' else 0):
            raise ValueError(f'Invalid profile field: {key}')
    for key in ('heroes', 'goods', 'formations', 'vars', 'region_stars', 'quest_progress', 'draws'):
        if not isinstance(data.get(key), dict):
            raise ValueError(f'Invalid profile field: {key}')
    if data.get('res_id') not in (18, 19) or not isinstance(data.get('role_name'), str):
        raise ValueError('Invalid character selection')
    if type(data.get('novice_completed')) is not bool:
        raise ValueError('Invalid novice completion flag')
    for key in ('claimed_quests', 'settled_battles'):
        if not isinstance(data.get(key), list):
            raise ValueError(f'Invalid profile field: {key}')
    for slots in data['formations'].values():
        if not isinstance(slots, list) or len(slots) != 5 or not all(isinstance(x, str) for x in slots):
            raise ValueError('A formation must preserve exactly five string slots')


class OpeningStore:
    """Locked copy-on-write transactions with atomic replacement and a previous-save backup."""
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.lock = threading.RLock()
        if self.path.exists():
            # Never silently reset corruption; operator can restore the .bak file.
            self.data = json.loads(self.path.read_text(encoding='utf-8'))
            validate_profile(self.data)
        else:
            self.data = new_profile()
            self._persist(self.data)

    def snapshot(self) -> dict:
        with self.lock:
            return deepcopy(self.data)

    def _persist(self, data: dict) -> None:
        validate_profile(data)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        previous = self.path.read_bytes() if self.path.exists() else None
        fd, tmp = tempfile.mkstemp(prefix=self.path.name + '.', suffix='.tmp', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write('\n')
                f.flush()
                os.fsync(f.fileno())
            if previous is not None:
                backup = self.path.with_suffix(self.path.suffix + '.bak')
                backup_tmp = backup.with_suffix(backup.suffix + '.tmp')
                backup_tmp.write_bytes(previous)
                os.replace(backup_tmp, backup)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    @contextmanager
    def transaction(self):
        with self.lock:
            candidate = deepcopy(self.data)
            yield candidate
            self._persist(candidate)
            self.data = candidate

    def create_role(self, name: str, selection: int) -> dict:
        if selection not in (0, 1) or not name.strip() or len(name.strip()) > 6:
            raise ValueError('Character needs a 1–6 character name and selection 0 or 1')
        with self.transaction() as d:
            if d['role_name']:
                raise ValueError('This profile already has a character')
            index = 18 + selection
            guid = f'hero{index}'
            d['role_name'], d['res_id'] = name.strip(), index
            d['heroes'][guid] = {'guid': guid, 'index': index, 'level': 1,
                                 'stars': 1, 'stage': 0, 'xp': 0,
                                 'params': [0, 0, 0, 0],
                                 'skills': {'A': 1, 'B': 1, 'BD': 1, 'MJ': 1}}
            # The first formation guide clicks the owned portrait to ADD the commander.
            # Pre-assignment would make that same click REMOVE it and strand the guide.
            d['formations']['0'] = ['', '', '', '', '']
        return self.snapshot()

    def save_formation(self, kind: int, slots: list[str]) -> None:
        slots = list(slots) + [''] * (5 - len(slots))
        if len(slots) != 5 or not slots[0]:
            raise ValueError('A formation requires a commander and at most five slots')
        with self.transaction() as d:
            nonempty = [x for x in slots if x]
            if len(nonempty) != len(set(nonempty)) or any(x not in d['heroes'] for x in nonempty):
                raise ValueError('Formation contains duplicated or unowned heroes')
            d['formations'][str(kind)] = slots

    def set_var(self, name: str, value: str) -> None:
        if not name or len(name) > 128 or len(value) > 1024:
            raise ValueError('Invalid player variable')
        with self.transaction() as d:
            pending = d.setdefault('pending_vars', {})
            unmet = (name == 'NG_10011E' and not d['draws']['gold']) or (
                name == 'NG_10031E' and d['heroes'].get(f"hero{d['res_id']}", {}).get('stage', 0) < 1)
            # These guide clicks happen before their action request. Persist completion
            # only with the action, so disconnect between click/request can resume safely.
            if value == '1' and unmet:
                pending[name] = value
            else:
                d['vars'][name] = value
                pending.pop(name, None)

    def begin_battle(self, region: int, difficulty: int = 1) -> dict:
        with self.transaction() as d:
            if not d['role_name']:
                raise ValueError('Create a character before entering a battle')
            if d['battle'] and not d['battle'].get('settled'):
                if d['battle']['region'] == region and d['battle']['difficulty'] == difficulty:
                    return deepcopy(d['battle'])
                raise ValueError('Another battle is active')
            if region == 99:
                if d['novice_completed']:
                    raise ValueError('The novice sequence is already complete')
            elif region in STORY_REGIONS:
                if not d['novice_completed']:
                    raise ValueError('Finish the novice sequence first')
                if region != 1001 and d['last_normal_region'] < region - 1:
                    raise ValueError('Previous story stage is not complete')
                if difficulty != 1:
                    raise ValueError('Elite opening stages are not supported yet')
                if not d['formations'].get('0', [''])[0]:
                    raise ValueError('Select a commander before entering a story stage')
                if d['stamina'] < 8:
                    raise ValueError('Insufficient stamina')
                d['stamina'] -= 8
            else:
                raise ValueError('Region is outside the supported opening')
            d['battle_sequence'] += 1
            d['battle'] = {'id': d['battle_sequence'], 'region': region,
                           'difficulty': difficulty, 'settled': False}
            battle = deepcopy(d['battle'])
        return battle

    def settle_battle(self, battle_id: int, won: bool, stars: int = 0,
                      coins: int = 0, xp: int = 0, goods: dict | None = None,
                      hero_xp: int = 0, player_levels: dict | None = None,
                      hero_levels: dict | None = None) -> bool:
        with self.transaction() as d:
            b = d['battle']
            if battle_id in d['settled_battles']:
                return False
            if not b or b['id'] != battle_id or b['settled']:
                raise ValueError('Settlement does not match an active battle')
            b['settled'] = True
            b['won'] = bool(won)
            b['stars'] = max(0, min(3, stars)) if won else 0
            d['settled_battles'].append(battle_id)
            if won:
                if b['region'] == 99:
                    d['novice_completed'] = True
                else:
                    d['last_normal_region'] = max(d['last_normal_region'], b['region'])
                    key = str(b['region'] * 10 + b['difficulty'])
                    d['region_stars'][key] = max(d['region_stars'].get(key, 0), max(0, min(3, stars)))
                    if b['region'] == 1003:
                        d['quest_progress']['1'] = 1
                d['coins'] += max(0, coins)
                d['xp'] += max(0, xp)
                while player_levels and d['level'] in player_levels:
                    required, stamina_gain = player_levels[d['level']]
                    if required <= 0 or d['xp'] < required:
                        break
                    d['xp'] -= required
                    d['level'] += 1
                    d['stamina'] = min(10000, d['stamina'] + stamina_gain)
                if b['region'] != 99:
                    for guid in d['formations'].get('0', []):
                        if not guid:
                            continue
                        h = d['heroes'][guid]
                        h['xp'] = h.get('xp', 0) + max(0, hero_xp)
                        while hero_levels and h['level'] in hero_levels:
                            required = hero_levels[h['level']]
                            if required <= 0 or h['xp'] < required:
                                break
                            h['xp'] -= required
                            h['level'] += 1
                for name, count in (goods or {}).items():
                    d['goods'][name] = d['goods'].get(name, 0) + max(0, count)
            elif b['region'] != 99:
                # Configured loss is one stamina rather than the full entry cost.
                d['stamina'] += 7
        return True

    def recruit(self, kind: str) -> tuple[dict, bool]:
        if kind not in ('silver', 'gold'):
            raise ValueError('Unsupported recruitment type')
        with self.transaction() as d:
            if d['level'] < 2 or d['last_normal_region'] < 1001:
                raise ValueError('Recruitment opens after the first story stage')
            is_new = d['draws'][kind] == 0
            if is_new:
                d['draws'][kind] = 1
                d['draws'][kind + '_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                if kind == 'silver':
                    d['goods']['GOODS48'] = d['goods'].get('GOODS48', 0) + 1
                else:
                    guid = 'hero31'
                    d['heroes'][guid] = {'guid': guid, 'index': 31, 'level': 1,
                        'stars': 1, 'stage': 0, 'xp': 0, 'params': [0, 0, 0, 0],
                        'skills': {'A': 1, 'B': 1, 'BD': 1, 'MJ': 1}}
                    pending = d.setdefault('pending_vars', {})
                    if 'NG_10011E' in pending:
                        d['vars']['NG_10011E'] = pending.pop('NG_10011E')
        return self.snapshot(), is_new

    def claim_quest(self, task_id: int) -> tuple[dict, bool]:
        with self.transaction() as d:
            if task_id != 1 or d['quest_progress'].get('1', 0) < 1:
                raise ValueError('Quest is not complete')
            is_new = task_id not in d['claimed_quests']
            if is_new:
                d['claimed_quests'].append(task_id)
                d['coins'] += 1000
                d['gems'] += 10
                d['goods']['GOODS104'] = d['goods'].get('GOODS104', 0) + 1
        return self.snapshot(), is_new

    def advance_slot(self, guid: str, slot: int) -> dict:
        if slot not in (1, 2, 3, 4):
            raise ValueError('Invalid advancement slot')
        with self.transaction() as d:
            h = d['heroes'].get(guid)
            if not h or h['index'] not in (18, 19) or h['stage'] != 0:
                raise ValueError('Only initial starter advancement is supported')
            params = h.setdefault('params', [0, 0, 0, 0])
            if not params[slot - 1]:
                material = ('GOODS42', 'GOODS51', 'GOODS51', 'GOODS48')[slot - 1]
                if d['goods'].get(material, 0) < 1:
                    raise ValueError('Insufficient advancement material')
                d['goods'][material] -= 1
                params[slot - 1] = 1
        return self.snapshot()

    def advance_hero(self, guid: str) -> dict:
        with self.transaction() as d:
            h = d['heroes'].get(guid)
            if not h:
                raise ValueError('Hero is not owned')
            if h['stage'] == 0:
                if h['level'] < 3 or h.get('params') != [1, 1, 1, 1] or d['coins'] < 250:
                    raise ValueError('Advancement prerequisites are not met')
                d['coins'] -= 250
                h['stage'] = 1
                h['params'] = [0, 0, 0, 0]
                pending = d.setdefault('pending_vars', {})
                if 'NG_10031E' in pending:
                    d['vars']['NG_10031E'] = pending.pop('NG_10031E')
        return self.snapshot()
