"""Read-only compare protected bytes after real mode-switch QA.

Produces a new report; never changes a profile, backup, APK or game setting.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def fingerprint(path):
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'size_bytes': path.stat().st_size, 'sha256': digest}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    if args.report.exists():
        raise SystemExit('Preserve existing report; choose a new output path')
    baseline = json.loads(args.baseline.read_text(encoding='utf-8-sig'))
    compared = []
    for before in baseline['protected_files']:
        path = args.runtime / before['relative_path']
        after = fingerprint(path) if path.is_file() else None
        compared.append({'relative_path': before['relative_path'], 'expected_sha256': before['sha256'], 'expected_size': before['size_bytes'], 'actual': after, 'unchanged': after is not None and after['sha256'] == before['sha256'] and after['size_bytes'] == before['size_bytes']})
    user_path = args.runtime / 'server/profiles/opening-user.json'
    user = json.loads(user_path.read_text(encoding='utf-8-sig')) if user_path.exists() else None
    pristine = user is not None and user['role_name'] == '' and user['level'] == 1 and user['xp'] == 0 and user['stamina'] == 90 and user['coins'] == 0 and user['gems'] == 0 and user['novice_completed'] is False and not any(user[key] for key in ('heroes','goods','formations','vars','pending_vars','region_stars','quest_progress','claimed_quests','settled_battles')) and user['draws'] == {'silver': 0, 'gold': 0} and user['battle'] is None and user['battle_sequence'] == 0
    report = {'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'baseline': str(args.baseline), 'protected_files': compared, 'all_protected_bytes_unchanged': all(item['unchanged'] for item in compared), 'user_profile': user, 'user_fingerprint': fingerprint(user_path) if user is not None else None, 'user_genuinely_uncreated': pristine}
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'all_protected_bytes_unchanged': report['all_protected_bytes_unchanged'], 'user_genuinely_uncreated': pristine, 'report': str(args.report)}))
    return 0 if report['all_protected_bytes_unchanged'] and pristine else 1

if __name__ == '__main__':
    raise SystemExit(main())
