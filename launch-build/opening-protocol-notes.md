# Opening protocol research — original client, static evidence only

## Scope / confidence

Research for `/home/user0/mhsy/mhsy-offline-revival`, using original `work/apk/Client_4201.dll` and generated `work/protobuf_serializer.dll`, the current `server/game_server.py`, and extracted Lua/config/XML. No Windows, emulator, live-server execution or main-source edits were performed by this researcher. These are static reverse-engineering findings, **not a claim that the complete opening is runtime-tested**.

Python tools were run with `PYTHONPATH=/home/user0/mhsy/.launch-deps`; use `python3` (there is no `python` executable). Later commands additionally used `PYTHONDONTWRITEBYTECODE=1`.

Do not trust `messages_full.json`'s `wire` values for strings/nested messages or its decoded nested CLR type names. Some examples are demonstrably incorrect (`CCMsgMainPlayer.player` is not `CMsgRequestServerType`). Generated serializer `WriteFieldHeader` plus getter / write calls are authoritative. `DataFormat=2` alone does **not** mean fixed32.

## Highest-priority corrections to legacy server

1. **C→S 1801 is player-variable persistence**, not a sign-in-info request. Sign-in request C→S is 1401; S→C response is 1801. MainPlayer `SetPlayerVaris` sends 1801 and legacy handler answers sign-in data. NG / MCPlay / movie progress is currently ignored.
2. **C→S 301 is ordinary / escort stage entry**. Must send S→C 401 FBInfo **before** 107 ChangeRegionRet; FBInfo is input to scene initialization, not merely an end-of-battle result.
3. **C→S 304 is empty request-back-main-city**. Novice victory sends it; reply requires city born position 103 before ChangeRegionRet 107 `{region_res_id:1}`. Normal transitions reuse MainPlayer; do not resend 102 every scene.
4. Once/daily task requests are **703 / 701**, reward claims are **704 / 702**. Legacy C→S 1101/1103 interpretation is wrong; these are equipment IDs in that direction. Initial task responses are S→C 1103/1101 and incremental responses S→C 1104/1102.
5. `build_task_info` taskId/finishTimes and `build_goods_update` count must use **varint**, not fixed32. Their exact generated serializers confirm it.
6. `CMsgDetailPlayerInfo.leftTimeToSecondLoginDay` tag36 is **varint**, not float/fixed32. Only battleDoggeConstant51 and battleBlockConstant52 are floats/fixed32 among those initial scalar fields.
7. Fresh NO-ROLE login: prefer 108 success + 1301 notify, **without 101 account-enter-ret yet**. 101 changes the login state to game state3, whereas 1301 changes it to creation state2, so sending both initially makes a race. After role creation, 101(false) drives entry into novice99.
8. Recruitment C→S is **2201 silver / 2202 gold**, S→C result2401, cooldown2402, ownership addition1204. Guide after1001 expects hero **31**, not merely another starter19.
9. No required protocol1200 was identified in the original client. Full IL constant scan found only animation state1200 in `FxDynamicModel.PlayAnimation` (0x8a9f4), not a Send or registered receive handler. Do not invent a1200 contract from outdated docs; preserve unknown-packet logging and inspect any actual sample independently.

## Framing

Existing server framing is reusable:

```
[totalLength:u32LE][msgId:u16LE][crc32(body):u32LE][serial:u16LE][protobuf body]
```

Header12 bytes, CRC standard zlib CRC32 over body. Numeric varint keys use wire0; strings and nested messages wire2; float32 wire5. Direction matters: identical IDs represent unrelated contracts in different directions.

## Contract table (verified generated Write methods)

Notation: `v`=varint; `s`=UTF-8 length-delimited; `m`=length-delimited nested; `f`=IEEE754 float32 wire5. Boolean is varint.

| Direction / ID | Body | Serializer evidence |
|---|---|---|
| S→C101 | `CSMsgAccountEnterRet`: dynID1:v, alreadyNewUserGuideFB2:bool, debug3:bool, mainRoleIndex4:v, svrCurTime5:s, isEnableHundredTower6:bool, isEnableHundredTowerSDDH7:bool, isEnableLP8:bool | Write0x5ad0c |
| S→C108 | `CCSMsgAccountEnterCheckRet`: ResultInfoCode1:v, account2:s, serverId3:s, extraParm4:s; success code1 | Write0x42bdc (legacy builder plus client handler) |
| S→C1301 | NotifyCreateRole, no body needed | client `OnNotifyCreateRole`0x264585 |
| C→S1001 | `CCMsgRequestCreateRole`: roleName1:s, selectID2:v; select0→hero18, select1→hero19 | client creation callsite / CreateRoleSetup |
| S→C1302 | `CCMsgRequestCreateRole_Ret`: retCode1:v; **success0** | `OnRequestCreateRole_Ret`0x27d8c4 |
| C→S102 | QuestFirstEnterRegion, empty | game-state OnEvent0x267e74, IL0x266433–0x26643c |
| S→C102 | `CCMsgMainPlayer`: dynID1:v,res_id2:v,name3:s,player4:m(`CMsgDetailPlayerInfo`) | Write0x1bcc8 |
| S→C103 | CCMsgSetMainCityBornPos: x1:f,y2:f,z3:f | OnSetMainCityBornPos0x26ed7c, float Vector3 constructor |
| C→S104 | CCMsgChangeRegion `{region_res_id1:v}`; means LevelLoadFinish | Write0x71d8; game-state OnEvent IL0x266446–0x266460 |
| S→C107 | CCMsgChangeRegion `{region_res_id1:v}` | Write0x71d8; OnChangeRegionRet0x26fa50 |
| C→S301 | CCMsgRequestEnterFB `{region_res_id1:v,level2:v}`; normal1 / elite2 | Write0x25ca8; EmBattleSystem0x12b918 |
| S→C401 | CCSMsgFBInfo: region_res_id1:v,JinBi2:v,Exp3:v,WuJiangExp4:v,WNSP5:v,YingPo6:v,dropGoods7:repeated m,needCheck8:bool | Write0x43a18 |
| nested FBInfo.dropGoods | CMsgDropGoods `{oriName1:s,count2:v}` | Write0x1f11c |
| C→S302 / S→C1001 | CCMsgResultFB `{result1:v,starCount2:v}`; victory1 / failure2 | Write0x2e774 /0x2ebc0; controller send callsites |
| C→S304 | RequestBackMainCity empty | novice controller0x35840 IL0x34425–0x34431 |
| C→S1801 | CMsgPlayerVaris `{VariName1:s,VariValue2:s,IsDeleteVari3:bool}` | Write0x50658; SetPlayerVaris0x60c24, DeletePlayerVaris0x60ce8 |
| C→S703 /701 | once/daily request, empty | MainPlayer.UnPackData0x5dbe8 IL0x5c906–0x5c923 |
| C→S704 /702 | CCMsgPrizeOneTask `{taskId1:v}` | Write0x1f70c; callbacks0x1de150 /0x1de188 |
| S→C1103 /1104 | CCMsgRequestOnceTask_Ret `{onceTaskInfo1:repeated m}` | element Write0x59c48 |
| nested COnceTaskInfo | `{taskId1:v,finishTimes2:v,delete3:bool}` | Write0x59c48 |
| S→C1101 /1102 | daily list / increment with repeated CDailyTaskInfo tag1 | element Write0x44534 |
| nested CDailyTaskInfo | `{taskId1:v,finishTimes2:v,isPrized3:bool}` | Write0x44534 |
| S→C301 | CCMsgShiningAwardItem `{oriName1:s,count2:v,isShining3:bool}`; count is new total | Write0x30e00, OnUpdateGoodsCount0x27166c → SetGoods |
| S→C501 | CCSMsgAttriUpdate `{type1:v,iValue2:v,strValue3:s}`; iValue is absolute, not increment | Write0x42eb8, MainPlayer.AttriUpdate0x5f40c |
| S→C1204 | CMsgAddWuJiang `{wjInfo1:m(CMsgWuJiang),isClientShow2:bool}` | Write0x4812c; OnAddWuJiang0x271bec |
| C→S2201 /2202 | CCMsgRequestDrawBaoXiang `{isSingle1:bool}` | Write0x24bd0; BuyTreasureSystem0x10c624 |
| S→C2401 | CCMsgRequestDrawBaoXiangRet `{type1:v,isSingle2:bool,awards3:repeated m,addSuiPian4:repeated m}` | Write0x24ca8; OnRequestDrawBaoXiangRet0x275830 |
| nested draw award | CCMsgDrawBaoXiangAwrad `{type1:v,equipments2:s,roles3:m,items4:m}`; type1 equipment,2 hero,3 item | Write0xab78; UI union discrimination |
| nested draw hero | CCMsgDrawBaoXiangRole `{index1:v,suiPianCount2:v,suiPianName3:s}` | Write0xada0 |
| nested draw item | CMsgGoods `{oriName1:s,count2:v,...}` | generated getters and UI reads; item count varint |
| S→C2402 | CCPlayerDrawBaoXiangUpdate `{lastJBFreeDrawTime1:s,lastZSFreeDrawTime2:s,freeJinBiDrawTimeLeft3:v,zuanShiTenDrawCount4:v}` | Write0x426d8; OnPlayerDrawBaoXiangUpdate0x2757ac |

### Attributes for 501

`NetProto.EAttriType` constants decoded from Msg.dll:

`1=current EXP`, `2=current VP`, `3=JinBi`, `4=RMB/diamonds`, `6=level`, `7=skill points`, `8=万能碎片/WNSP`, `15=英魄/YingPo`.

`MainPlayer.AttriUpdate` directly assigns new iValue. For example type3 assigns mCurJinBi; type4 assigns mCurRMB. Send totals, not deltas. Hero attributes are a separate S→C601 CCSMsgWuJiangAttriUpdate: GUID1:s,Type2:v,iValue3:v,strValue4:s (Write0x43644). Hero types1 EXP,2 level,3阶段,4星级;9..12 skill levels.

### Persistent player / hero snapshot

`CMsgDetailPlayerInfo` Write0x49724 verifies:

- guid1:v, account2:s, level3:v, curexp5:v, curvp6:v, curRMB7:v, jinbi8:v.
- lastmainFBnormal9:v, lastmainFBdifficult10:v, worldchatfreetimes11:v, skillpoints12:v, WNSP13:v, JJCJF14:v.
- lastJBFreeDrawTime30:s, lastZSFreeDrawTime31:s, freeJinBiDrawTimeLeft32:v, mainRoleIndex35:v, leftTimeToSecondLoginDay36:v, account_create_time48:s.
- battleDoggeConstant51:f, battleBlockConstant52:f.
- owned heroes101:repeated m, goods102:repeated m, FBStar103:repeated m, Equipments106:repeated m, Varis109:repeated m, resourceFBData115:repeated m. Direct Write0x49724 evidence: get_FBStar IL0x485b9 → loop → ldc.i4.s103 at0x485de → wire2 → WriteFieldHeader0x485e2. (An early parent message incorrectly associated FBStar with106; this is corrected.)
- Fresh snapshot must not prepopulate all NG variables with1 or set lastnormal1010 / player level30. Those skip the requested opening.
- Keep necessary timestamps in `yyyy-MM-dd HH:mm:ss`, not empty. Account creation is parsed by MainPlayer.UnPackData.
- Supply resource FB records5/6/8/9/10 as legacy server does to avoid unrelated city UI null data.

`CMsgWuJiang` Write0x5826c:

```
guid1:s,index2:v,level3:v,jieduan4:v,curexp5:v,stars6:v,
jieduan_type_1_para7:v,..type_4_para10:v,
skillindex_1_level11:v,..skillindex_4_level14:v,fightpower15:v,
EquipList16:repeated m,addfightpower17:v,equipSoul18:m,...
```

Persist real starter18/19 at starting level / skills rather than novice trial companions. `CMsgFBStar` Write0x4ca8c: res_id_and_level1:v (`region*10+difficulty`),star2:v,FBPlayTime3:v,curDayBuyTime4:v. On reload include earned FBStar records and maximum completed normal/elite region.

## Required sequencing

### A. Fresh no-role login → creation region98

1. Standard INIT / account101 C→S handshake; do not confuse request101 with response101.
2. For a fresh profile without a role send **S→C108 success** and **S→C1301 empty**; omit S→C101 until role exists.
3. `ᜲ.OnNotifyCreateRole`0x264585 closes LoginChoiceServerUI and sets state2. Creation state's entry method0x27d6b0 loads scene98 / `Scene_choose_02`.
4. Client submits1001 `{roleName,selectID}`. Validate / persist role and permanent starter / starting PVE formation.
5. Send1302 `{retCode:0}`. Explicit `08 00` is a safe nonempty zero-valued protobuf body if serializer-null edge handling is a concern.
6. Then send101 `CSMsgAccountEnterRet` with `alreadyNewUserGuideFB=false`, selected mainRoleIndex1 for18 /2 for19 and valid server-time string. Exact create-state handler0x27db30 selects99 and changes state3.

**Why the additional101 matters:** creation success handler0x27d8c4 only invokes `CreateRoleSystem.ShowEnterAni` with callback0x27dbe8 that posts event661. Creation state's `OnEvent`0x27d79c branches only73/74/75 despite registering661; it does not itself change state3. S→C101 create-state handler does. Server sending101 immediately after1302 can shorten animation; exact animation-preserving timing still needs parent runtime verification.

101 `alreadyNewUserGuideFB=false` selects static region99; true selects1. Game-state static ctor0x27cfb2 defines99/1. This boolean **does not mutate** GlobalSetup.mNewUserFBActive: that field comes from config. Extracted GlobalSetup_CH says `新角色进行新手副本 1`, and `是否开启引导 1`.

### B. First novice scene99 load / trial roster

Game-state entry0x267bb4 loads selected region. On scene event74 (`OnEvent`0x267e74): constructs Region, initializes difficulty, then if first-load flag true sends5401 empty,5402 empty,102 empty and clears first-load flag. On subsequent scene changes it sends104 `{region_res_id}` instead.

On C→S102:

- Send103 city born position (required for later transition / returning login) then102 full persistent player snapshot.
- Send201 PVE formation, then other safe necessary incremental UI data after MainPlayer exists (legacy450/4602 if reused).
- Answer proactive703/701 task requests once MainPlayer's complete-member dictionaries exist, before quest-reward guide is encountered.
- Existing legacy5401/5402 responses may be reused; they are ancillary equipment transformation operations, not novice state completion.

`OnQuestFirstEnterRegionRet`0x26edb0 uses region's own BornBos for region type11; other first-entry types use cached103. Novice's real position is `(24.01001,199.42,-3.75)` from99_gk.xml, not city position.

**Trial roster is entirely client-generated:** `NewUserFBController.GenerateMainTeam`0x3509c obtains config by MainPlayer.ResId and uses config.id + config.ids. `GenerateWj`0x351ec creates Guid.NewGuid and temp WuJiang/equipment data from config. It does not require persistent five-hero ownership / formation. NewUserFB_WjAttriCfg:

-18 starter → temporary18,19,27,24,31.
-19 starter → temporary19,18,27,24,31.
-Level20,star1,jieduan3,skills and equipment supplied by config (equipment average20).

### C. Novice completion → city1

NewUserFBController0x35840 sends C→S304 empty at end (IL0x34425–0x34431) and opens loading UI. No302 is required for novice completion.

On304 while session region99:

1. Atomically persist novice_done=true; do not mark it simply because any304 arrived from an unrelated scene/login.
2. Send103 city position `(-1.12,301.52,15.42)`.
3. Send107 `{region_res_id:1}`.
4. Client loads1. Scene event74 sends104 `{region_res_id:1}` and reuses existing MainPlayer; do **not** send a second102 unless deliberately rebuilding login state.
5. Refresh pending initial tasks / forms/UI state on scene-ready signal where needed.

103 must precede107: city scene initialization reads cached born vector immediately. `OnChangeRegionRet`0x26fa50 posts event112, swaps previous/current region and calls0x26fa98 to LoadScene.

Returning login with novice_done uses101 `alreadyNewUserGuideFB=true` and correct role index. Extracted config mNewUserFBActive=1 means no initial304 is sent by login here. If another package/config sets it0, login can send304 before game-state handler registration and sets a skip-load flag; timing requires separate handling / verification.

### D. Stage1001 /1002 / escort1003 entry

Client creates/saves PVE formation via202, then sends301 `{region_res_id,level}` from EmBattleSystem0x12b918. Validate owned formation and unlocked stages; store active battle metadata / one-use reward marker.

Send in this order:

1. **401 CCSMsgFBInfo** for target region, nonempty body, needCheck=false.
2.103 target born position if sending it (client battle spawns also use Region.BornBos; this keeps cached position correct).
3.107 target region.
4. Client sends104 target region after scene assets load. Do not postpone401 until104.

Why401 before107 is mandatory:

- Loot manager `ᜉ.OnGetFBInfo`0x27ec8d stores FBInfo cache and applies needCheck to GameManager.IsServerCal.
- Game-state OnEvent74 creates Region then calls loot manager method13390 /rva0x27e648. This copies the cache into Region.FbInfo only if region IDs match.
- Region.enter calls method13391 /rva0x27e704, computes drop distribution and **clears the cache**.
- Sending401 after those points does not retrofit Region.FbInfo and risks settlement null dereference.
- needCheck=true activates server-authoritative fight synchronization; use false for playable local opening.

Target positions:

-1001 `(4.4,23,-12.6)`.
-1003 `(19.25,33.65,129.85)`;1002 comes from1002_gk.xml.

Configured normal awards / starting leveling:

| region | JinBi | playerEXP | heroEXP | first-clear fixed items |
|---|---:|---:|---:|---|
|1001|55|8|32|GOODS42×1,GOODS104×2|
|1002|72|8|34|GOODS51×1,GOODS104×2|
|1003|72|8|34|GOODS51×1,GOODS48×1,GOODS104×2|

RegionDropList lines43–45 and PlayerLevelInfo.ini are authoritative configuration. Starting level1 needs6EXP;1001's8EXP gives level2/remainingEXP2, unlocking recruitment (`DrawBaoXiangConfig` system level2).1002 then gives lv2EXP10;1003 crosses lv2's12 threshold to lv3EXP6 (assuming no other awards).

Loot manager adds configured first-clear fixed drops locally; avoid duplicating them inside401.random dropGoods. Server still must persist/grant fixed rewards once on victory.

### E. Normal / escort victory settlement

Normal BattleController0x161b4 sends302 `{result:1,starCount:max(1,3-deadCount)}`. Escort HuSongBattleController0x25ce0 does the same for region type15. Failure sends result2.1003 has no separate necessary server escort messages: client spawns/moves ProtectTarget from1003_gk.xml and uses ProtectTarget-only triggers. Its XML targets `(85.12,33.31,94.52)`.

On valid302 result1:

1. Atomically complete active battle once, persist max stars, lastnormal/elite, currency / EXP / heroEXP / first-clear goods, and quest completion.
2. Send501 absolute level6/EXP1/coins3/VP2 as appropriate and hero updates601 if XP/level changes.
3. Send301 per acquired goods with **new owned total count**, not acquired delta.
4. Send1001 CCMsgResultFB `{result:1,starCount}` while controller's event111 listener is active.
5. Send1104 completed once tasks (`delete=false`, finishTimes satisfied), not claimed removal yet.
6. Wait for player's304 before changing to city; do not warp away during settlement UI.

`OnMsgResultFBRet`0x26fa00 dispatches event111 synchronously with deserialized result. Local win callbacks0x1631c(normal) /0x25e4c(escort) update client FBStar and LastMainFBNormal themselves before victory UI; persistent snapshot on future login must preserve this. No dedicated progress501 enum exists for LastMainFBNormal.

### F. Recruitment after1001

GuideLogic.lua183–241:

- NG_10011E opens tavern, optionally silver single draw when GOODS48 absent, then gold single draw / confirm.
- NG_10021B explicitly calls `SetEmBattleFirstWuJiangID(31)`. Gold opening draw must yield hero31 for unmodified guide.

C→S2201=coin/silver draw;2202=diamond/gold draw; request `{isSingle:true}` for these guide clicks. BuyTreasureSystem0x10c624 uses selection1→2201,selection2→2202.

Hero result sequencing:

1. Persist guaranteed hero31 (stable unique GUID, level1, correct stars/skills) and draw/cooldown state.
2. Send1204 CMsgAddWuJiang with wjInfo and `isClientShow=false`. `OnAddWuJiang`0x271bec creates persistent WuJiangData and inserts it in owned list.
3. Send2401 `{type:2,isSingle:true,awards:[{type:2,roles:{index:31,suiPianCount:0,suiPianName:""}}]}`.
4. Send2402 cooldown/free-count state with valid date strings. First draw free / costs should follow chosen original rules; do not accidentally lock mandatory guided draw.

Ownership must be sent before2401 because recruitment UI resolves hero by index from MainPlayer's owned heroes. Do not set isClientShow=true if2401 already triggers the recruitment showcase, to avoid duplicate hero-show overlays.

Silver can award a genuine configured item (guide checks GOODS48). For item union `{type:3,items:{oriName:"GOODS48",count:1}}`, update owned inventory via301 before2401.

### G. First quest reward and persistence

OnceTaskConfig.txt line18 task1:

- Type1 normal clear, target1003, required count1.
- Reward0playerEXP,1000JinBi,10RMB,GOODS104×1.
-1001 does not complete quest1.1003 victory completes it but does **not** auto-claim.

Initial703 request →1103 active unclaimed task records. At1003 win →1104 `{taskId:1,finishTimes:1,delete:false}`. Claim C→S704 body `{taskId:1}`:

- Validate complete, not claimed; atomically persist claim plus currency / item total.
- Send501 type3 absolute newJinBi,501 type4 absolute newRMB.
- Send301 GOODS104 absolute owned total and shining=true if desired.
- Send1104 `{taskId:1,finishTimes:1,delete:true}`; task2 etc can be appended with delete=false if valid.
- Duplicate/replayed704 must not award twice; persisted claimed tasks must not reappear on future703 list.

`OnUpdateOnceTask`0x271ab0 removes known task if delete=true; updates finishTimes otherwise; can also add new task entries. Be aware unknown-task delete=true is added as a deleted task record rather than skipped: don't send remove records for tasks never presented unless needed.

Variable C→S1801:

- Set `{VariName:"NG_10011B",VariValue:"1"}`, MCPlay etc: update per-profile dict atomically. Client already applies local change, no dedicated reply is required.
- Delete `{VariName:key,IsDeleteVari:true}` removes key.
- Persist values as **strings**, including numericMCPlay.
- On102/901 reload encode dictionary as CMsgDetailPlayerInfo tag109 repeated CMsgPlayerVaris with name1/value2 wire2.
- Do not answer arbitrary1801 with sign-in payload1801; this is a direction collision.

## Concrete body fixtures

All below are protobuf **body only**, not12-byte frames. Explicit default zeros are valid even though protobuf writers may omit them.

```
C→S301 normal1001: 08 e9 07 10 01
C→S301 normal1002: 08 ea 07 10 01
C→S301 normal1003: 08 eb 07 10 01
S→C107 city1:      08 01
S→C401 minimal1001:08 e9 07
S→C401 1001 awards55/8/32/needCheckfalse:
                   08 e9 07 10 37 18 08 20 20 40 00
C→S302/S→C1001 win3stars: 08 01 10 03
C→S704 task1:      08 01
S→C1103 task1 pending: 0a 04 08 01 10 00
S→C1104 task1 completed:0a 04 08 01 10 01
S→C1104 task1 claimed:  0a 06 08 01 10 01 18 01
C→S1801 NG_10011B=1:
  0a 09 4e 47 5f 31 30 30 31 31 42 12 01 31
S→C2401 single gold hero31:
  08 02 10 01 1a 06 08 02 1a 02 08 1f
S→C301 GOODS104 total1 shining:
  0a 08 47 4f 4f 44 53 31 30 34 10 01 18 01
S→C501 new JinBi1000:08 03 10 e8 07
```

Minimal401 carries no monetary reward and is only a diagnostic fixture; actual opening should provide configured rewards. No runtime assertion is made for the fixtures here.

## Evidence locations

- Client IL: original Client_4201.dll method RVAs above. Duplicate obfuscated type names exist; resolving by RVA is safer than first type-name match.
- Serializer: protobuf_serializer.dll generated `Write` RVAs above; checked `WriteFieldHeader` constants rather than stale summaries.
- Lua: `LuaRoot/Region/RegionLogic.lua` city MCPlay lines30–110, novice movies391–435,1001 joystick/ultimate437–488,1002 assists491–512,1003 movies/invincibility555–603.
- Lua: `LuaRoot/Guide/GuideLogic.lua` opening begin/end150–264; `LuaRoot/net/Msg.lua` directional enum names confirm request703/704 vs response1103/1104, but newer messages require C# callsite/registration evidence.
- XML/config: GameData/RegionList,RegionDropList,PlayerLevelInfo.ini,NewUserFB_WjAttriCfg,OnceTaskConfig,DrawBaoXiangConfig,RegionLogic/99_gk.xml,1_gk.xml,1001_gk.xml,1003_gk.xml.

## Remaining runtime verification items for parent

- Exact1302→101 timing that preserves creation animation while leaving state98; static flow requires101, but no live test was run here.
- Verify region98/99 scene assets in the selected patched package; server protocols cannot repair a missing prefab or patched scene loader.
- Ensure501/301/601 absolute updates arrive in an order compatible with victory animation; static setters are absolute and do not perform grants.
- Ensure initial task dictionary is ready when703 request answer processed, especially novice99 first initialization.
- Check reconnect from interrupted stage returns to an intentionally safe saved region with full consistent snapshot rather than resuming unsupported mid-fight synchronization.
- Any actual1200 frame requires fresh sample/body evidence; no protocol1200 Send/receive registration exists in the inspected original DLL.
