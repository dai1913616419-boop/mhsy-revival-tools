# Fresh opening: recruitment, normal starter state, guide restoration, and first advancement

Read-only research, except this note. No server implementation, maincode, Windows files, APK, save, or live service changed by this research agent. `/home/user0/AGENTS.md` read. dnfile/dncil used with `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/user0/mhsy/.launch-deps:...` to avoid creating research artifacts. Parent owns implementation and emulator acceptance.

## Executive recommendations

1. Restore only `GuideClickSystem.Open` and `Show` in the generated client: two one-byte changes, verified against original `Client_4201.dll`. Preserve SDK/login bypasses, announcement bypass, price null guard, and normalized prompt stubs.
2. Fresh owned roster = selected hero18 or19 only, level1/star1/white phase0. Tutorial99 uses loaned boosted heroes from `NewUserFB_WjAttriCfg.txt`; those are not normal owned roster. Do not preseed31.
3. Give first guided silver draw `GOODS48 ×1`, first guided gold draw hero31. These awards are inferred from guide dependencies, not a recovered server draw table. Emit inventory/roster mutations before recruitment presentation reply.
4. Persist authoritative draw flags independently of `NG_10011E`: Lua marks that flag at the gold click, possibly before the server handles the draw.
5. Claim quest1 after1003 for +1000coins/+10gems/GOODS104×1, no playerXP. Do not mark `NG_10031E` complete merely for claiming it: the guide immediately continues into the starter's legitimate first advancement.
6. Implement904 material application and905 promotion. Both starter choices need the same totals: GOODS42×1, GOODS51×2, GOODS48×1, then250coins and hero level≥3. Configured first-clear drops plus guided silver draw provide all materials without fabricated rewards.

## Sources and confidence

Project root: `/home/user0/mhsy/mhsy-offline-revival`.

- Authoritative client tables: `work/apk/luapack_extracted/GameData/{CreateRoleSetup.txt,DrawBaoXiangConfig.txt,GlobalSetup_CH.txt,PlayerLevelInfo.ini,WuJiangLevelInfo.txt,WuJiangBaseAttri.ini,NewUserFB_WjAttriCfg.txt,RegionDropList.txt,OnceTaskConfig.txt,WuJiangJinJie.txt,WuJiangJinJieCommon.txt,GoodsList.txt}`.
- Guides: `work/apk/luapack_extracted/LuaRoot/Guide/{GuideLogic.lua,GuideInterface.lua,GuideSystem.lua,GuidePrefeb.lua}`.
- Original client: `work/apk/Client_4201.dll`. Generated current client inspected: `/home/user0/mhsy/launch-build/Client_launch.bin` (Unity bundle, embedded PE begins0x2080).
- Contracts: `work/messages_full.json`, cross-checked against actual `work/carve/msg/Msg.dll` AND the Msg.bytes assembly inside generated `mhsy_local_latest.apk`, asset `assets/bin/Data/3f1bdaed5855fd64ab18e8be3793d5fb`, embedded PE begins8400 decimal/0x20d0. Recruitment contracts/attribute enums agree.
- Callsite candidates: `output/09b_泛型调用点.json`. Registration confirmed directly in original method RVA0x264888. Do not blindly trust inferred `type` in `output/09_消息号映射.json`: some entries are wrong or null.
- Extraction warning: `messages_full.json` reports strings/nested objects/list element types inaccurately (e.g. roles as `AssemblyConfigurationAttribute`, items as `AssemblyDescriptionAttribute`, list:System.Object). Actual roles = `CCMsgDrawBaoXiangRole`, items/addSuiPian = `CMsgGoods`, awards = repeated `CCMsgDrawBaoXiangAwrad`. Numeric/string/nested wire types below are independently confirmed. Stale comments equating DataFormat2 with fixed32 must not override these verified varint contracts.

## Starter state and economy

### Owned versus loaned heroes

`CreateRoleSetup.txt`: choice0→hero18 黑剑士; choice1→hero19 闪光骑士. The boolean selectID in create request follows this mapping. Legacy player `mainRoleIndex` is1-based (1 for18,2 for19), not raw18/19 and not0.

`WuJiangBaseAttri.ini`: initial star for18/19/31 =1. Normal starting phase should be0 (white), not legacy build_wujiang phase1/5stars/skill10/level30. Send star1 explicitly: WuJiangInfo constructor initially sets1, but then overwrites it from `CMsgWuJiang.get_stars`, so omitted stars become0. Normal skill levels1 are a safe restoration baseline, not an original server starting-skill table recovered here; in particular skill2 should be≥1 when phase1 unlocks skillA.

Normal owned roster should contain only the selected starter until the gold draw. `GuideInterface.searchRoleId` finds the first owned hero17..20 and stores `firstLogin`; pre-owning18+19 makes starter identification ambiguous for choice19.

Tutorial99 config is separate:

| selected | loaned companions | tutorial stats |
|---|---|---|
|18|19,27,24,31|avg level20,stars1,phase3,progress0; A16/B11/passive0/MJ20/WS0|
|19|18,27,24,31|same|

Tutorial equipment avg level20/star0, EQ0023..EQ0033. This is not a justification to grant those heroes/equipment permanently after99.

### Stamina and draw settings

- Guides enabled1; new role performs tutorial1.
- Player level1: next-levelXP6, normal stamina cap90, level-up stamina+20. Level2 threshold12/cap91/+20; level3 threshold18/cap92/+20.
- Global stamina hard cap10000; regen1 per300sec; normal battle failure stamina loss1. Normal regeneration cap and global hard cap are different: level-up gains may exceed the normal regen cap.
- Recruitment unlock level2.
- Coin single10000/ten100000; gem single265/ten2650.
- Coin free single count5, cooldown5minutes; gem free single cooldown2880minutes.
- Empty last free draw timestamp means free eligibility. Alternatively use valid old `yyyy-MM-dd HH:mm:ss`. Use full saved counter state in each2402; omitting the other timestamp resets its client value.
- No authoritative initial coins/items grant list was found in these client configurations. Legacy `build_player`'s10000coins is a demo implementation choice, not recovered provenance. Empty inventory and90stamina support the guide, provided free timestamps/counters are correct. A modest starter coin policy must be documented as a restoration choice. +199 battle coins/+1000 quest coins suffice for the250 advancement cost even from0coins.
- Keep initial GOODS48 absent if the full silver tutorial is desired; guide deliberately skips silver steps if already owned.

## Opening guide dependencies

- `NG_10011B`: key10011 on `DaTingUI`, guides entry1001.
- `NG_10011E`: key10021 on `DaTingUI`, after1001. Tavern sequence: entry→silver button→silver single if GOODS48≤0→reward acknowledgment→gold button→gold single→hero modal confirmation→tavern return. Gold single step `d8.isComplete=true`; completion does NOT mean the server has committed the roster.
- `NG_10021B`: key10021 on `GuanKaZhuJieMian`, guides1002 and explicitly `SetEmBattleFirstWuJiangID(31)`.
- `NG_10031B`: key10031, guides1003 escort.
- `NG_10031E`: key10041, first claims claimable once-task reward(s), then opens starter details/advancement, uses each zero progress slot, opens promotion preview and confirms promotion; only `d14` isComplete.
- `GuideInterface.guideLine` skips only when exact var value is string `"1"`, records `_C` child step counters, and `executeGuide` sets completion vars at user clicks. Preserve client1801 CMsgPlayerVaris{1:name,2:value} writes as durable strings; do not blanket set NG_* to1.
- In firstLogin search, empty means unset; avoid preseed0 or"1" (neither is the selected hero).
- Prompt-state stubs beingfalse do not disable `GuideLogic.guide_OnceTask`: it calls the separate count API. Once-task dataset must be populated with valid config IDs; invalid IDs can recreate config lookup NREs.

## Recruitment protocol: exact IDs and bodies

All numeric fields below use varint; strings/nested messages use length-delimited wire2. Bodies below exclude transport framing.

| direction/ID | contract | body |
|---|---|---|
|C→S2201|CCMsgRequestDrawBaoXiang|tag1 isSingle(bool); type1 silver is selected by ID|
|C→S2202|same|tag1 isSingle(bool); type2 gold selected by ID|
|S→C2401|CCMsgRequestDrawBaoXiangRet|1:type(int32,1silver/2gold),2:isSingle(bool),3:repeated awards,4:repeated addSuiPian(CMsgGoods)|
|S→C2402|CCPlayerDrawBaoXiangUpdate|1:lastJBFreeDrawTime(str),2:lastZSFreeDrawTime(str),3:freeJinBiDrawTimeLeft(int32),4:zuanShiTenDrawCount(int32)|
|S→C1204|CMsgAddWuJiang|1:wjInfo(CMsgWuJiang),2:isClientShow(bool)|
|S→C301|CMsgGoods|1:oriName(str),2:absolute owned count(int32)|

Single request = `08 01`. Ten request may be empty or `08 00`; empty meansfalse, not single. Request contains no cost/free flag or transaction ID.

Nested award discriminator:

```
CCMsgDrawBaoXiangAwrad:
  1 type = 1 equipment | 2 hero | 3 goods
  2 equipments = equipment GUID string (not original item name)
  3 roles = CCMsgDrawBaoXiangRole{1:index(int32),2:suiPianCount(int32),3:suiPianName(str)}
  4 items = CMsgGoods{1:oriName(str),2:count(int32)}
```

First hero31 should have suiPianCount0; duplicate hero can return fragments with index31/suiPianCount>0/suiPianNameGOODS119. GOODS119 is hero31 fragment; synthesis needs10 for1star, not a substitute for directly owning the tutorial hero.

### Required ordering and duplicate safety

`OnRequestDrawBaoXiangRet` RVA0x275830 only posts event629. It does not mutate roster or inventory. BuyTreasureSystem event629 calls reward renderer; renderer RVA0x10e70c immediately looks up acquired hero by index/equipment by GUID. Missing roster logs and then dereferences null. Therefore:

1. Validate/persist draw, cost/counter, inventory or one new hero atomically.
2. Emit301 for changed goods and/or1204 for the new hero BEFORE2401. Use isClientShow=false: recruitment UI itself shows the hero acquisition modal.
3. Emit2402 full draw counters;501 currency if paid; then2401 single award.

`OnAddWuJiang` RVA0x271bec checks duplicateGUID, but only logs before still calling WuJiangData.Add. Never emit1204 twice for already-synced hero31 on retry in one connection. Reconnect uses full102/901 roster. Independent persistent guided_draw_done + roster presence protect against NG flag timing and duplicate reward grants. No client request transaction ID exists, so subsequent normal draws need a deliberate policy distinct from replaying the guided award.

### Exact sample bodies

```
301 GOODS48 absolute count1:
0a 07 47 4f 4f 44 53 34 38 10 01

2401 silver single GOODS48×1:
08 01 10 01 1a 0f 08 03 22 0b 0a 07 47 4f 4f 44 53 34 38 10 01

2401 gold single hero31 (not duplicate):
08 02 10 01 1a 06 08 02 1a 02 08 1f

1204 minimal hero31 GUID="hero31",level1,stars1,skill1=1,whitephase0,isClientShow=false:
0a 10 0a 06 68 65 72 6f 33 31 10 1f 18 01 30 01 58 01 10 00
```

Minimal1204 example omits zero/default fields, optional skill2..4 and calculated fight power. For actual gameplay use your normal hero builder with every persisted skill/stat, not legacy high-level builder.

## Roster, attribute, XP, and first reward updates

`CMsgWuJiang` tags:1GUID(str),2index,3level,4jieduan(enum0white/1green),5curexp,6stars,7..10phase-slot progress,11..14skill1..4levels,15fightpower;16repeated timestone info;17addfightpower;18equipSoul;19repeated suiteffectid. Numbers here are varint.

S→C501 CCSMsgAttriUpdate{1:type(enum),2:iValue(int32),3:strValue(str)}; absolute values, not deltas:

-1player curexp,2stamina,3coins,4gems,6playerlevel,7skillpoints.

S→C601 CCSMsgWuJiangAttriUpdate{1:GUID(str),2:Type(enum),3:iValue(int32),4:strValue(str)}; absolute values:

-1hero curexp,2level,3phase,4stars,5..8phase-slot progress,9..12skilllevels,13fightpower.

Do not confuse battle display reward401 `{1:region_res_id,2:JinBi,3:Exp,4:WuJiangExp,7:dropGoods,8:needCheck}` with actual501/601 updates or full reconnect roster. Persist rewards and emit absolute state updates separately. Explicit varint0 fields are useful for reset/remove states, even though protobuf default semantics allow omission; ensure entire message body stays nonempty.

First-clear table facts:

| stage | coin | playerXP | heroXP | guaranteed goods |
|---|---:|---:|---:|---|
|1001 normal|55|8|32|GOODS42×1,GOODS104×2|
|1002 normal|72|8|34|GOODS51×1,GOODS104×2|
|1003 normal|72|8|34|GOODS51×1,GOODS48×1,GOODS104×2|

All three stamina cost8. Optional random1003goods need not be fabricated as guaranteed. GOODS104 is sandwich, +400heroXP when used; quest reward adds one sandwich but it must not automatically grant400XP.

Player thresholds6,12,18; hero thresholds30,50,70. From level1/XP0 and rewards granted only to deployed heroes:

| milestone | player | selected starter | hero31 |
|---|---|---|---|
|after1001|L2 XP2|L2 XP2|not yet owned|
|after1002|L2 XP10|L2 XP36|L2 XP4 if deployed|
|after1003|L3 XP6|L3 XP20|L2 XP38 if deployed|

Table level-up stamina gain20 should be applied against global hard cap, not clamped to regen cap91. If starting90 and no elapsed regen: enter1001→82; first level-up→102;1002→94;1003→86 then level-up→106. Original server code wasn't recovered, so server-side refill behavior remains a config-based implementation choice, not emulator verification.

Quest1 (`OnceTaskConfig.txt` row1) unlock level1, no previous task, normal stage1003/finishcount1; reward playerXP0,coins1000,gems10,GOODS104×1. Persist task claimed independently of NG flags. First list/update IDs1103/1104; claim-specific handler details belong to parent's server work.

Example501 level2 = `08 06 10 02`;501playerXP2 = `08 01 10 02`;601hero18XP2 = `0a 06 68 65 72 6f 31 38 10 01 18 02`;601hero18level2 changes Type to2.

## Legitimate automatic advancement after quest claim

Added at parent's request to keep the restored guide from leaving UI locked after the first quest reward.

### Configured costs, materials, and eligibility

White phase0 promotion requires hero level3 and250coins (`WuJiangJinJieCommon.txt` phase0). All four white slot counts must be1/complete. Both18/19 have identical material totals, although slot2/3 stat effects differ:

| slot | hero18 configtype | hero19 configtype | white material/count | progress601 Type |
|---|---:|---:|---|---:|
|1|101100|101100|GOODS42×1|5|
|2|301100|302100|GOODS51×1|6|
|3|306100|304100|GOODS51×1|7|
|4|204100|204100|GOODS48×1|8|

1001 provides42;1002+1003 provide two51; silver or1003 provides48. First battle+quest coin total1199 from starter0 is enough, and starter reachesL3 from deployed battleXP. Do not boost levels or invent extra materials to bypass this path.

### Request904: use a material in one slot

Client `WuJiangDetailSystem` RVA0x2362cc sends:

```
C→S904 CCMsgWuJiangOneTimeJinJie_Type:
  1 WuJiangGuid string
  2 JinJieNumberofWuJiang int32 = SLOT INDEX1..4, NOT configtype ID
```

Client checks owned material count>0 and current slot progress/requiredcount<1. Server should validate owned hero, white phase0 in opening scope, selected slot1..4, progress0, materialcount≥1; consume one material, set progress1 and persist atomically. Reply via authoritative state pushes only:

-301 material new absolute count (can be0; encode count0 explicitly as `10 00`).
-601 `{GUID,Type=4+slot,iValue=1}`. MainPlayer Type5..8 sets slot progress and posts event101 with GUID/slot, refreshing detail UI. No dedicated904reply contract/handler was found.

Example904hero18slot1 = `0a 06 68 65 72 6f 31 38 10 01`;601hero18slot1complete = `0a 06 68 65 72 6f 31 38 10 05 18 01`;301GOODS42remaining0 = `0a 07 47 4f 4f 44 53 34 32 10 00`.

Duplicate904 on already-complete white slot must not consume again. Persist each applied slot so restarting between material clicks is safe. Reject unsupported later phases explicitly rather than interpreting their material table as white.

### Request905: commit white→green

Clicking initial detail-page advancement confirm opens `JinJieChengGong` PREVIEW locally (event244); no server commit yet. Its final confirm sends905 from `WuJiangJinJieSuccessSystem` RVA0x23f9b8 and closes preview:

```
C→S905 CCMsgWuJiangGuid{1:WuJiangGuid string}
```

Server validates phase0, heroL≥3, all four progress1 and coins≥250. Atomically deduct250coins, phase→1, reset persisted four progress slots0. Emit501coinabsolute, then601 `{GUID,Type3,iValue1}`. No dedicated905reply found.

Important: MainPlayer.WuJiangAttriUpdate RVA0x5fc40 Type3 AUTOMATICALLY resets all four client progress fields0 before assigning newphase. It calls `SkillOpenTiShiUISystem.AddOpenTiShiUI(oldphase,newphase)`, posts event102GUID, and resumes waiting Lua viaevent648 if needed. Thus ONE stage601 suffices; extra four reset601messages are unnecessary. SkillA unlock modal is legitimate continuation, not an error. Keep persisted skill2level≥1 so unlocked skill can function.

Example905hero18 = `0a 06 68 65 72 6f 31 38`;601hero18greenphase1 = `0a 06 68 65 72 6f 31 38 10 03 18 01`.

Client marks NG_10031E at final guided confirmation; this may precede server905 commit. Acceptance must assert actual phase1,250coin deduction, reset slots, claimed quest and all save state after relogin, not merely NG completion. Avoid committing green twice on duplicate905; no duplicate coin deduction. Allow server rejection without falsely persisting phase.

## Selective client restoration: verified exact bytes

### GuideClick can be restored with only two bytes

Original versus generated bodies:

| method | RVA | fat header bytes | CodeSize | body total bytes | generated bundle first IL absolute offset | restore |
|---|---|---:|---:|---:|---|---|
|GuideClickSystem.Open|0x15cdfc|12|144|156|0x15d088|2a→18 (`ldc.i4.2`)|
|GuideClickSystem.Show|0x15d368|12|201|213|0x15d5f4|2a→02 (`ldarg.0`)|

Original PE method file offsets0x15affc/0x15b568; original first IL0x15b008/0x15b574. Generated embedded PE begins0x2080; method header absolute0x15d07c/0x15d5e8. Each complete method body differs from original at exactly relative offset12, and no header/EH/local signatures differ. `Client_patched2.bin` has pristine identical GuideClick bodies.

Safe build implementation: locate embedded PE with dnfile, assert exact owning class/method/RVA, fat header12 and CodeSize144/201, assert original fullbody differs from generated only at byte12, then restore that original byte. Or copy exact full original bodies after verifying stable metadata/token layout. Restore BOTH: Show calls Open then accesses the constructed UI, so leaving Open earlyret while restoring Show can null-dereference. No relocating methods, rewriting EH, or metadata recompilation is needed for these two methods.

Preserve the original bundle prefix and all existing unrelated modifications. The two absolute offsets above are diagnostic only; production patch should locate byRVA and assert bytes rather than assume wrapper layout.

### Prompt stubs need more than first-byte restoration; leave them for opening

Generated `/home/user0/mhsy/launch-build/Client_launch.bin` normalizes:

- DailyTaskPromptState0x60dbc original code110/body140 including EH; normalized fat flags0x3003,maxstack1,CodeSize2,locals0,IL16 2a.
- OnceTaskPromptState0x60e48 same original code110/body140/EH; normalized similarly.
- TeQuanFuLiPromptState0x60ed4 original code84/body96; normalized CodeSize2/maxstack1/locals0.

Historical patches merely overwrote first two ILbytes and left code size/EH/locals. The TeQuan patch demonstrably fails dncil parsing due leftover operand bytes; old Mono also rejected it. Restoring only first instructions in CURRENT normalized client would leave CodeSize2/cleared locals/EH and is invalid. A real restoration requires full original header+IL+EH body and resolving original NRE dependencies first. Opening need not restore these prompt-dot methods; quest UI and separate claimable-count API still work. Don't regress normalized launch fix.

### Preserve these unrelated patches

Full original/generated PE diff scan found tutorial implementation modifications only in Open/Show. Other changed methods retained: AndroidSdkConnector.StartLogin0x3bcc; LoginSystem.Open0x1a68c0 and login nested0x1a78d4; InGameNoticeSystem.Open0x16046c; DrawBaoXiangProperty.UpdateZS10PriceFromServer0x6f09f; three prompt methods. Remaining diffs are metadata/strings, not additional tutorial method patches. Price updater's guard avoids null server-priceInfo and allows config prices; no need to restore it for guided single draws.

## Resource safety and what byte restoration cannot guarantee

Original APK directly verified to contain:

- Guide_Click.prefab: `assets/bin/Data/1b8f2bea77461434f83c9ee40a9abee5`,18892bytes. Binary contains PressArea,QuanPingZhuDang,Up,Down,Left,Right,TiShiNormal,TiShiMirror,WenZhi,GuidePressArea names expected by client.
- GuidePressArea.mat,Guide_heidi.png,Guide_heidi2.png,xinshouyindao.png,NGUIFont.prefab,JiChuTuBiao_New_1.prefab/_2,Guide_Prompt.prefab.
- ChouBaoXiang.prefab,ChouBaoXiangWuPing_Item.prefab,WuPinTuBiao.prefab,TouXiang.prefab,HuoQuJiangPingZhangShi.prefab.

Manifest and AssetExtraInfo declare corresponding names/dependencies. Thus historical comment 'missing resources lock city' is not proven for this generated APK. Open0x15cdfc creates Guide_Click; Show0x15d368 configures area then layout0x15cfc0; original click-handler0x15d5a0 closes overlay only when hit falls in prescribed region. Restoring bytes does not independently establish runtime resource resolution, screen-coordinate sizing, input pass-through, Lua lifecycle, or collider behavior. Parent should verify actual click advances guide and restores normal input at real emulator resolution; don't silently set guide flags to escape a stuck overlay.

## Recommended acceptance assertions

- New profile, no demo overwrite; selected starter only normal ownership; loaned99 roster does not persist.
-99 tutorial→1001, player reachesL2; guided silver/gold actually sends2201/2202, silver gives48, gold mutates roster31 before2401.
-1002 formation can select31;1003escort playable; complete quest1 and claim exactly once, reward persists after reconnect.
- Continue actual guided904slots1..4; verify42−1,51−2,48−1 and matching progress pushes;905cost250,phase1,slots reset,skillA unlock, guide completes without forged NG state.
- Retry904/905/recruit/quest claim doesn't duplicate materials/currency/hero; partial material application resumes after restart.
- Relog full102/901 values equal persistent account/starter/31levelXP, phase, skills, inventory, counters, quest state, guide vars; UI remains interactive.
- Do not claim live completion based on static disassembly or bytes matching: emulator input/persistence acceptance belongs to parent.
