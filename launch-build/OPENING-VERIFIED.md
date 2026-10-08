# MHSY local opening — verification and launch guide

## Launching

Use the Windows desktop shortcuts:

- **MHSY Opening** — original fresh-player tutorial, separate persistent `server/profiles/opening-user.json`.
- **MHSY Local Game** — preserved existing demo `server/save.json`.

The launcher installs the appropriate signed APK with `adb install -r`, verifies the installed APK fingerprint, and dispatches the existing BlueStacks **Rvc64 / Android11 / emulator-5554** instance. It does not uninstall the app, clear app data, reset a role, or import a QA save. A normal desktop launch may request Windows UAC approval. Only the two named shortcuts were updated; legacy launch commands are not the maintained mode-safe entrypoints.

For Opening, select **黑剑士 / Black Swordsman** or **闪光骑士 / Flash Knight**, enter a name (the dice generates one), and press **开始游戏**. The final user profile is intentionally uncreated so the player—not the QA run—makes this choice.

## Real gameplay verified

| Feature | Evidence / result |
|---|---|
| Both character choices | Original native portrait/name/Start creation succeeded on isolated Black and Flash profiles. |
| Original novice/prologue99 | Journal, movement waypoints, basic attack, skill-A lesson, trial companion switch and boss were played with actual input. Server received actual304 and persisted completion. Trial heroes were not permanently granted. |
| Correct city onboarding / formation | A fresh role owns only its selected LV1 hero, starts with five empty formation slots, and the original portrait lesson adds—not removes—the commander. Native verified for both choices. |
| Story1001 movement and ultimate | The movement prompt does **not** stop the battle timer; bounded native inputs were used. Both original charged-ultimate prompts appeared with an alive boss and highlighted portrait. Independent captures proved the automatic clock pause. Actual portrait presses triggered **断空连斩** (Black) and **电光火石** (Flash), spent energy and resumed combat. Flash's subsequent real settlement at01:40 proves the clock resumed from01:47. |
| Recruitment | Original guided draws gave saved hero ownership and inventory. Recruited hero31 is a **ranged magic Cat Archer**, not a healer. |
| Story1002 / escort1003 | Both earned-character routes completed through actual native victories; all three story clears saved three stars. Escort outcome was real, not an automatic-win injection. |
| First quest | Quest1 claimed once; configured1000 coins,10 gems and item104 reward persisted. |
| Advancement | Original equipment/advancement UI consumed configured materials; the250-coin transaction promoted each starter to stage1 with equipment params cleared. |
| Persistence / cold / reconnect | Earned Black passed three cold launches and actual native reconnect; earned Flash passed its full route and cold login. Interrupted unsaved stories abort with the configured1VP cost and no invented rewards. |

The preserved earned profiles each retain LV3/XP6,949 coins/10 gems, completed99, three-star1001–1003, quest1 claimed, silver/gold draws1 each, promoted starter and recruited hero31. Black stamina104; Flash stamina106. All milestones came from real outcomes.

### Exact original ultimate evidence

- Black: `opening-black-fresh-1001-charge-attempt.png`, `opening-black-fresh-1001-ultimate-frozen.png`, `opening-black-fresh-1001-ultimate-cast.png`.
- Flash: `opening-flash-lesson-1001-charge-attempt.png`, `opening-flash-lesson-1001-ultimate-frozen.png`, `opening-flash-lesson-1001-ultimate-cast.png`, `opening-flash-lesson-1001-settlement.png`.

Black's new isolated lesson attempt later lost its connection before settlement. Its prompt/cast proof is valid, but **that lost attempt did not earn saved stars or rewards**; native reconnect correctly aborted it. The older earned Black route already supplies genuine saved progression evidence. Flash's new isolated lesson attempt did settle normally.

## Mode-switch release check

The actual named desktop links were dispatched inside the existing user0-pc interactive session, using the user's existing elevated token. This proves shortcut routing, installed APK selection, service lifetime and native rendering/login; **it does not prove a visible UAC prompt was clicked**. QA JSON deliberately records native UI separately from launcher exit.

- **D1 Demo:** correct demo APK fingerprint, `/Other/serverlist.txt`, native本地服. An old pre-fix Demo process accepted connections but stalled before login. After strict owned-process recovery with the **same arguments and save**, genuine native city/HUD rendered爱弗里达 LV30,10000 coins,0 gems,0VP.
- **O1 Opening:** actual shortcut exit0; correct opening APK, `/Other/opening.txt`; only the settled test9003 service switched to the separate USER profile. Native新手体验服 → both-choice creator. Real101 →108 +1301(success0); no role creation or102 scene entry.
- **D2 Demo:** actual shortcut exit0; correct demo APK/endpoint; existing Demo service retained. Native original city/HUD returned with the same demo role/resources. A redundant dialogue batch briefly opened the optional bracket UI; it was exited normally without a match, reward or save edit.
- **O2 Opening:** actual shortcut exit0; correct opening APK/endpoint; same USER service retained. Native新手体验服 → original two-choice creator (Android PID7400), without pressing Start. Fresh logged101 →108 +1301 after launcher/SSH exit proves the service remains usable. USER created_at12:55:19 and SHA25620716f0442026b83e79ad99a594cae18baa639942fbf77801848d4493a06316f are byte-identical to O1; no role, ownership, currency, vars, draws or battle were created.

After Demo recovery, HTTP PID24344 and Demo PID27912 retained their exact executable/creation/arguments across switching. O1 created Opening PID24056 against `opening-user.json`; D2/O2 retained it. The initial dead historical HTTP22124/Demo16776 were recovered only after reproducible real failures, so they are not falsely described as unchanged. All nine protected save/profile/backup files have identical SHA256 **and sizes** to the predeployment baseline. The four completed temporary QA dispatch tasks were removed after identity/state checks; maintained launch tasks and all three services remain running.

## Fixes and checks

- Minimal Mono-safe identifier getter avoids the old Android identifier/JNI crash; both signed APK variants retain original assets and the same local signing identity.
- Fresh permanent formation is empty until the original ADD lesson; wire fixtures follow serializer IL, not guessed XML formats.
- Atomic profiles use durable replace/backups; idempotent reward and interrupted-battle handling preserve earned progress.
- Optional console logging no longer decides packet/HTTP request success. Closed/broken/invalid stdout failures are guarded narrowly, while durable file logging and original protocol/resource responses remain intact.
- Original opening regressions plus console-loss additions: **57 passing**. Validated native input batch: **6 passing**. Real HTTP do_GET/version-route regression covers three console failure types. Existing compatibility/launcher checks were not rerun without source changes.
- QA wrapper changed only to wait on the direct launcher process, not its persistent descendants; parse/AST regression failed before and passed after. Maintained launcher/installer source hashes were unchanged by this QA-only fix.

No game AI/energy/tutorial-state hacks, manual live packet injection, save/star edits, forced victory, app-data clear, signing-key delivery, model change or permission change were used.

## Scope and known limitations

This restores and verifies the requested **opening route**, not every late-game/online feature. Legacy SDK analytics/network warnings may remain. Demo emitted a nonfatal optional BOB cache-save `DiskFullOper`/null-prefab warning on one login; it still rendered the native city. Do not interpret the verification as error-free support for every original online system.

Detailed chronological evidence is retained in `OPENING-PROGRESS.md`.

Final deliverables/evidence:
- `mode-qa-protected-baseline-20261003T032531Z.json` — all nine protected predeployment byte fingerprints and semantic summaries.
- `mode-qa-preservation-final.json` — successful read-only post-QA comparison and pristine USER profile.
- `mode-qa-final-readonly-audit-20261003T041801Z.md` — independent final byte/identity/shortcut/protocol/UI audit with full hashes and source-qualified findings.
- `mode-qa-D1-recovered-hud.png` / `mode-qa-D2-returned-city.png` — authoritative Demo city results.
- `mode-qa-O1-creator.png` / `mode-qa-O2-creator.png` — original uncreated USER creator on both switches.
- `launch-game-mode.ps1` / `install-mode-shortcuts.ps1` — maintained mode-safe launcher and shortcut installer, exact copies deployed to Windows.

**Requested opening objective verified.** Final native game is running at USER character creation; no Start press was performed. Optional online/late-game systems remain outside this verification.
