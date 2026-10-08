"""Read authoritative opening costs/rewards and level thresholds from bundled tables."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / 'work/apk/luapack_extracted/GameData'


def table(filename, header_key):
    columns = None
    result = []
    for line in (ROOT / filename).read_text(encoding='utf-8').splitlines():
        cells = [c.strip() for c in line.split('\t')]
        while cells and cells[0] in ('', '#'):
            cells.pop(0)
        if columns is None:
            if header_key in cells:
                columns = cells
        elif cells and cells[0].isdigit():
            result.append(dict(zip(columns, cells)))
    if columns is None:
        raise ValueError(f'Header missing in {filename}')
    return result


PLAYER_LEVELS = {int(r['角色等级']): (int(r['到下一级的升级经验']), int(r['到下一级的精力增加值']))
                 for r in table('PlayerLevelInfo.ini', '角色等级')}
HERO_LEVELS = {int(r['等级']): int(r['到下级经验']) for r in table('WuJiangLevelInfo.txt', '等级')}
DROPS = {(int(r['场景ID']), int(r['难度'])): r for r in table('RegionDropList.txt', '场景ID')}
REGIONS = {int(r['场景ID']): r for r in table('RegionList.txt', '场景ID')}


def rewards(region, difficulty, first_clear):
    row = DROPS[(region, difficulty)]
    goods = {}
    if first_clear:
        for i in (1, 2, 3):
            name = row[f'首次通关必掉物品原始名_{i}']
            count = int(row[f'首次通关必掉物品数量_{i}'])
            if name != '0' and count:
                goods[name] = goods.get(name, 0) + count
    # Guaranteed regular drops are authoritative; optional RNG drops are not yet included.
    for i in range(1, 11):
        if int(row[f'物品_{i}_掉落概率']) == 10000:
            name, count = row[f'物品_{i}_原始名'], int(row[f'物品_{i}_数量'])
            if name != '0' and count:
                goods[name] = goods.get(name, 0) + count
    return {'coins': int(row['金币']), 'xp': int(row['主玩家经验']),
            'hero_xp': int(row['武将经验']), 'goods': goods}
