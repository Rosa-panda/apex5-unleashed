# ADR-017 官方逐游戏适配导入 + 通用震动联动 + 自定义 exe

日期：2026-09-18

## 背景
用户三项反馈：
1. 当前"游戏库"只是给游戏圈一个预设，不是**一游戏一配置**。官方空间站的适配是逐游戏手工调配的细致参数。
2. 需要**默认震动联动模式**：游戏震动时扳机有反馈、不震动时无反馈，官方已实现，比较万能。
3. 特殊版本游戏（列表有但版本不同）要让用户**自己选 exe** 定位，不能完全软件掌控。

## 调研结论（官方逆向，2026-09-18）

### 官方逐游戏适配库
`C:\Program Files\Flydigi Space Station\Configs\Controller\Trigger\adapterTriggerGames.json`（137KB）：
~75 款游戏，每款含 `ProcessGameName(s)`、`ExeName`、`IsVibration`、`VibFilter`、`VibParams`（5 值 CSV）、`PwmScal`、`VibType`、`Scenes`（手感说明文案）、`ModDownLoadUrl`（深度 Mod，另需下载 XGameMonitor.exe 等，闭源）。

### 震动联动的本质 = cmd 0x52 SyncWithGrip（设备端固件行为）
- 官方扳机类型枚举 `AdapterTriggerType {Normal,Race,Sniper,Recoil,Lock,Vibration}`（Vibration=5）。
- `ForceTriggerConfigSyncWithGrip(side, bindType, filter, scale, stroke, pressureLevel, strength, frequency)` → cmd 82，8 字节参数。
- `VibType=2` 与 blob 力反馈区 `Type==5 → byte[1]=2` 对应：**扳机绑定握把震动马达，固件自动把游戏震动路由到扳机**——无需 Hook 游戏，任何发震动的游戏都生效。这就是"万能模式"。
- 参数映射（推定，签名逐位对齐）：`bindType=VibType(2)`，`filter=VibFilter`，`scale=PwmScal`，`stroke/press/strength/freq = VibParams[0..3]`。待真机验证（见风险）。

### 深度 Mod（XGameMonitor / ForzaDualSense 等）不复刻
官方对艾尔登法环/赛博朋克等用**独立 Mod 程序**读游戏内存/数据口实现事件级手感，闭源闭协议。我们导入这些条目仅作档案展示（标注"官方Mod暂不支持"），不下载不运行。

## 决定
1. **导入器** `app/officialimport.py`：官方 JSON → 用户游戏档案（`%APPDATA%\...\games\`），
   每款游戏带 `vib` 字段 `{filter,scale,stroke,press,strength,freq}` + `scenes` 说明 + `official: true` 标记。
   `IsNeedDownMod` 的条目标注 `mod_only`。exe 匹配键同时收 `ProcessGameName` / `ExeName`（含/不含 .exe 变体）。
2. **档案应用逻辑** `gameprofiles.apply_game()`：有 `vib` → 双侧 `bind_grip`；有 `preset_id` → 套预设；
   前台切走且无命中 → 解绑（或回落通用联动，见 3）。自动切换与手动套用走同一条路。
3. **通用震动联动**：`GameProfiles.universal_vib`（bool）+ `POST /api/vib/universal`。
   开启时立即生效并作为"无档案前台"的回落；默认参数取官方敏感型（filter=1, scale=10, stroke=0, press=1, strength=100, freq=15）。
4. **自定义 exe**：`POST /api/games/{gid}/exe {exe: [...]}`——内置档案复制为用户档案后改写，
   前端卡片提供文件选择器（input accept=".exe"）。匹配仍走进程名（前台窗口进程），选 exe 即录进程名。
5. 分发合规：官方 JSON 属飞智数据，导入器读**本机已装空间站**的文件转换，不在仓库内再分发原始库（R2 商标同理）。

## 后果
- 游戏库从"预设索引"升级为"官方手工适配库 + 用户档案"两层；卡片显示官方参数徽标与手感说明。
- 通用震动联动一键开，任何游戏立刻有"震→扳机"反馈。
- cmd 82 参数映射若真机验证不符，只需改 `vib→grip params` 一处映射函数。

## 风险
- ~~VibParams→cmd82 映射是签名对齐推定，未经总线抓包实证~~ **已真机验证（2026-09-18）**：战地6 参数
  （filter=1, scale=10, stroke=0, press=1, strength=100, freq=15）经 `test_grip_real.py` 绑定 + 震动脉冲，
  用户确认扳机随节奏反馈、停震静止。细腻度弱于官方（测试用开关脉冲替代游戏震动，非映射问题），调参后续迭代。
- Mod 型游戏（艾尔登法环等）我们只给震动联动兜底，手感覆盖度低于官方 Mod（用户已知悉）。
- 实现/测试补充（同日自检修复）：① `match()` 用户档案优先于同名内置（导入升级/自定义 exe 副本遮蔽内置）；
  ② `save()` 的 gid 与内置同名撞车时加 `-user` 后缀（防 `all()` 里整条替换内置）；
  ③ 前台切到「有档案但无 vib 无预设」的游戏时不再残留上一游戏的绑定（统一走通用回落/解绑）。
