# Verified Opening and mode-safe launch tooling

Start with [OPENING-VERIFIED.md](OPENING-VERIFIED.md), the final verification report. [OPENING-PROGRESS.md](OPENING-PROGRESS.md) retains the chronological work record; [LAUNCH-NOTES.md](LAUNCH-NOTES.md) is the historical first Demo launch, not the current mode-safe entrypoint.

## Repository split

- **mhsy-offline-revival (private):** source, existing legally held client/config research archive, selected screenshots and detailed QA reports.
- **mhsy-revival-tools (public):** identical self-written server/tool sources and research documents only. No client binaries, original config tables/Lua, game screenshots, signing material or local saves are published. Screenshot/report names in the final document refer to private evidence, not files bundled with the public checkout.
- Newly generated APKs/assemblies, signing key/certificate, active profiles and before-reconnect/cold profile copies remain local. The private repository's already-tracked historical Demo save is unchanged.

## Build layout and dependencies

Run build commands from a repository root in **WSL**, not from this directory. `prepare_launch.py` uses its own private checkout's `work/apk/` if available; otherwise it uses a sibling directory named `mhsy-offline-revival`. Keep both checkouts side by side for public-tool use. Build outputs go to that invocation's `launch-build/`; runtime deployment goes to `/mnt/c/mhsy-local` (`C:\mhsy-local`).

The private inputs include the original APK, `Client_patched6.bin`, `Client_4201.dll`, and extracted `GameData`. The public repository alone cannot build a client or run the Opening state/protocol suites. Do not add those inputs to the public repository.

Python server runtime: standard library only. Build/analysis dependencies: `dnfile`, `dncil`, `cryptography`.

```bash
# Dependency setup only if not already installed; obey your network/proxy policy.
python3 -m pip install --target .launch-deps dnfile dncil cryptography

# MUTATING: rebuilds an APK and deploys runtime files. Not needed to launch
# the already-verified installation; do not rerun during ordinary mode switching.
PYTHONPATH="$PWD/.launch-deps" python3 prepare_launch.py --mode demo --host 192.168.1.104
PYTHONPATH="$PWD/.launch-deps" python3 prepare_launch.py --mode opening --host 192.168.1.104
```

Builds retain the existing local `launch-build/local-signing-key.pem` and certificate when present. **For an already-installed client, preserve and securely back up its original signing identity.** A fresh clone does not contain that identity; a newly generated key cannot replace the installed signed app with `install -r`. Never work around this by uninstalling/clearing data, and never upload signing material.

## Maintained Windows entrypoints

Deploy `launch-game-mode.ps1` and `install-mode-shortcuts.ps1` to `C:\mhsy-local` along with both already-built APKs. Review the verified-machine defaults first: `C:\Python312\python.exe`, BlueStacks **Rvc64 / Android 11**, bundled `HD-Adb.exe`, `emulator-5554`, and interactive user `user0-pc`. These are installation-specific, not universal defaults.

The shortcut installer updates only **MHSY Local Game** (Demo) and **MHSY Opening** (Opening), without launching or modifying a save. The launcher may request UAC, serializes mode switches, checks listener ownership/arguments, uses `adb install -r` and installed-APK fingerprints, and does not clear app data or logcat.

- HTTP update/version/server list: **80**.
- Existing Demo: **9001**, `server/save.json`.
- Opening: **9003**, `server/profiles/opening-user.json`.

Opening owns only the selected starter, keeps five empty permanent formation slots until the original ADD lesson, persists guide variables atomically, and grants progression from native outcomes. Temporary novice heroes are not permanently granted. Unsettled interrupted stories abort at the configured one-stamina cost, without rewards. Combat remains client-local; the legacy Demo's forced-win workaround is not used by Opening.

`Launch-Game.cmd`, `start-servers.ps1`, and `launch-emulator.ps1` are historical launch helpers; use the maintained dual-mode shortcuts instead. `android_control.py launch` deliberately clears logcat, so it is unsuitable when preserving QA logs. Native gesture helpers can change gameplay/profile progress; do not execute them as harmless smoke tests.

## Tests (no need to replay completed live verification)

These commands document the repeatable regression suites; committing/pushing does not require replaying the game or rebuilding APKs.

```bash
# Standard-library server handler/state/wire suites, with authorized private
# GameData present under this checkout's work/apk/luapack_extracted/GameData:
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s server -p 'test_opening*.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s server -p 'test_update_logging.py' -v

# Pure mocked input/cold-login helpers, no emulator interaction:
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s launch-build -p 'test_native_input_batch.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s launch-build -p 'test_play_story1001.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s launch-build -p 'test_cold_login.py' -v

# Actual-client byte inspection, no APK install or gameplay:
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/.launch-deps" python3 launch-build/test_device_identifier.py launch-build/Client_opening.bin
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/.launch-deps" python3 launch-build/test_prompt_stubs.py launch-build/Client_launch.bin

# Windows parser/pure-helper checks only, through the existing ssh windows
# connection. No launcher, installer, emulator or service is executed:
PYTHONDONTWRITEBYTECODE=1 python3 launch-build/test_mode_launchers.py
```

`debug/invoke-mode-shortcut-qa.ps1` and `debug/run-mode-shortcut-child.ps1` are archived real-shortcut QA helpers, not ordinary launchers: they register/dispatch QA work and can change the active mode. PID-specific one-off stop/restart scripts were deliberately not included. The final report preserves the D1 initial failure/recovery, Black isolated attempt without settlement, and native storage exception; it does not claim clean first-attempt success or error-free gameplay.

No verified runtime, APK, save, service or shortcut must change merely to commit/push these sources.
