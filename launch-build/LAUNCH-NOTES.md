# Verified local game launch — historical initial Demo report

> Historical record of the first Demo launch. For the maintained dual-mode entrypoints and final Opening/gameplay results, read [OPENING-VERIFIED.md](OPENING-VERIFIED.md) and [README.md](README.md). The legacy command and initial limits below are not the current Opening launch instructions.

## Current result

The game is installed and running in BlueStacks Android 11 on the Windows host. Verified local-server login, rendered main city, Challenge panel opening, and return to the main city. Screenshots: `main-city-final.png` and `challenge-verified.png`.

This is a launch verification, not a full gameplay/economy restoration. The included character save is used in a separate runtime copy.

## Start again

Double-click **MHSY Local Game** on the Windows desktop, or run:

```bat
C:\mhsy-local\Launch-Game.cmd
```

This starts/reuses this project's servers and launches the game in the interactive Windows session. Once the login screen appears, close the announcement and click **进入游戏**. If the arena bracket appears, click its X and then **退出** to return to town.

- Emulator: BlueStacks 5.22.166.1003, Android 11 (`Rvc64`), Hyper-V retained.
- Native translation verified: `armeabi-v7a` is in the device ABI list.
- Windows Python: existing `C:\Python312\python.exe`, version 3.12.6.
- ADB: bundled `C:\Program Files\BlueStacks_nxt\HD-Adb.exe`, device `emulator-5554`. Use it consistently to avoid version conflicts with the other installed ADB.
- Local ADB is enabled; remote ADB is not enabled.
- Build dependencies: dnfile, dncil, cryptography and transitive dependencies installed under workspace `.launch-deps` through Socket Firewall. No global Python-package upgrade is required.

## Runtime and preserved data

- Windows runtime: `C:\mhsy-local`.
- Active save: `C:\mhsy-local\server\save.json`.
- Seed-save backup: `C:\mhsy-local\server\save.original.json`.
- Server logs: `C:\mhsy-local\server\logs`.
- Client log capture: `C:\mhsy-local\client-logcat.txt`.
- Original source repositories, original APK, historical patched APK, client generations, and original save were not modified.

The running HTTP and game services were started through managed SSH jobs in this session. They are intentionally left running. The desktop launcher can start them again if those jobs stop. Closing BlueStacks does not stop the servers.

## Endpoints

The client, update resource, and server list consistently use **192.168.1.104**:

- HTTP update/version and server-list service: port 80.
- TCP game service: port 9001.
- Debug UDP console: loopback port 9002.

The APK's update domain was patched in the correct Qihoo resource, so Android root and hosts bind mounts are unnecessary. If the Windows LAN address changes, rebuild the APK and update the server list. A Windows firewall rule `MHSY-Local-Game` permits local-subnet TCP 80/9001 for the project Python executable. The copied update server rejects paths escaping its static roots; `/../save.json` returned 404 in verification.

## Client repair discovered during launch

The initial generation-6 client failed during city loading with:

```text
InvalidProgramException: Invalid IL code in
MobileGameDemo.MainPlayer:TeQuanFuLiPromptState (): IL_0007: ldloc.1
```

The historical patch changed the first two bytes to `ldc.i4.0; ret` but retained the old method CodeSize and exception metadata. Mono still validated leftover IL.

The generated client normalizes `DailyTaskPromptState`, `OnceTaskPromptState`, and `TeQuanFuLiPromptState` to two-byte method bodies, clears obsolete locals/exception sections, and preserves all method RVAs. Only the generated client is changed. The actual-client regression check failed before this repair and passed after it; the emulator then entered the city and its Challenge UI successfully.

Run the regression check:

```bash
PYTHONPATH="$PWD/.launch-deps" python3 launch-build/test_prompt_stubs.py launch-build/Client_launch.bin
```

Rebuild for the configured host:

```bash
PYTHONPATH="$PWD/.launch-deps" python3 prepare_launch.py
```

The build uses a persisted local signing key, allowing `adb install -r` upgrades without uninstalling or clearing app data. Keep `local-signing-key.pem` private and backed up. Do not share it.

## Known remaining limits

- The arena bracket appears on login and some arena entries are incomplete; two atlas warnings were observed.
- Manual movement, reward/inventory persistence, realistic resource consumption, and battle settlement still have the research-project limitations identified in the code review.
- The existing 83-second forced victory is a demo workaround, not a verified real battle-result implementation.
- No claim is made that every dungeon, task, shop, or combat system works.

## Installer provenance

BlueStacks installer checksum and Windows Authenticode signature were verified before installation. Expected/downloaded SHA256:

`DBE8B99D3D06F520865D7ADD1C8651B4841D55BEF07FB04C9F2D025263ADCAB7`

The publisher was Now.gg, INC. Installer source:

https://ak-build.bluestacks.com/public/app-player/windows/nxt/5.22.166.1003/e0cbf0a49445273dc3c94ced970fd7d4/FullInstaller/x64/BlueStacksFullInstaller_5.22.166.1003_amd64_native.exe

The cached installer remains in the Windows Downloads directory. Hyper-V, VirtualMachinePlatform, and WSL were not disabled.
