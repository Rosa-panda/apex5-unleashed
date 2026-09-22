# ADR-030 拓展键完整映射：固件表 + 软件键盘注入双通道

日期：2026-09-22
状态：已采纳

## 背景

用户反馈「重构后拓展键不能用」。排查结论（2026-09-22）：

1. 重构（ADR-029 B/F 批次）设备侧文件逐字节零差异（`git diff e8fe78f HEAD` 覆盖
   engine/extkeys/protocol/rawstream/macro/keymonitor/transport 全空），重构不可能是诱因。
2. 固件键表映射（ADR-019 通路）已恢复并经被动对时探针实测生效：m3 按压→同秒
   gamepad HID 输出 0x10（LB）、m4 按压→0.05s 后输出 0x20（RB）。
3. m2→Start(9) 输出 0x20 不是异常：官方 ControllerKey 枚举里 Select(6)/Start(9) 与
   Menu(24)/Back(28) 是四个不同的键。手柄物理菜单键=Menu(24)→0x80，Start(9) 是另一
   逻辑键；视图/菜单/C/Z 类目标在桌面和多数游戏里本就不显形——「看起来没反应」。

## 官方逆向结论（spacestation decomp 实锤）

官方空间站让六键生效走**双通道**：

- **手柄目标**（LB/RB/视图/菜单/C/Z…）→ 写固件键表（0xA3 族），与我们 ADR-019 通路
  完全同源（ControllerKey 枚举 18-23=M1-M6，目标值逐一吻合）。
- **键盘/鼠标目标**（KeyMapType_Keyboard / MapKeyboardKeyId）→ **不写固件**，PC 端
  软件注入：`KeyboardMouseInjectRunner.InjectKeyboardSimulator` 吃私有流 KeyStatus
  （0xEF 同源的映射前按压态），查 `_keyboardMapper` 后经 `FeizVkeyMouHelper` →
  `FeizVKBComm.dll` → `FeizVKB64.sys`/`FeizVMO64.sys` 内核虚拟键鼠驱动注入。

即：官方软件里 M 键「映射到键盘按键在游戏里可用」靠的是 PC 侧注入，不是固件。

## 决策

1. **双通道同构复刻**：
   - gamepad 模式 → 写固件键表（复用 `extkeys.ExtKeyMapper.set_targets`，写→读回
     校验→162 应用→166 保存，备份逻辑不变）。
   - keyboard 模式 → 固件表写透传 255（防双重触发），后端订阅 0xEF extkey 事件做
     边沿检测（按下/松开），经 `softmap.key_event`（SendInput）注入。官方用内核
     驱动是为了过反检测，我们用 SendInput（softmap 既有通路），不装第三方驱动。
2. **配置持久化**：`%APPDATA%\Apex5Unleashed\extkeymap.json`，六键每键
   `{mode: passthrough|gamepad|keyboard, target?, key?}`。
3. **默认值 = 老行为**：M1→视图(6) M2→菜单(9) M3→LB(10) M4→RB(11) LM→C(16)
   RM→Z(17)，全部 gamepad 模式——与「重构之前一直好好的」状态一致。
4. **0xEF 流需求**：任一键为 keyboard 模式时 `rawstream.demands["extkeymap"]=True`
   （ADR-028 修订 2 登记表加一消费者）；全透传/gamepad 时不占流（防手柄不休眠）。
5. **应用时机**：POST /api/extkeys/mapping 时落两条通道；固件表在 flash 持久
   （166 保存），重连无需重写。不做 attach 自动重写（写表有备份语义，避免开机
   静默改用户固件配置——留待真实需求再加）。
6. **边沿检测在订阅方**（`extkeymap.Runner`）：engine extkey 事件是「位图变化才发、
   带当前按下名单」，Runner 内部维护上次按下集合，差集即按下/松开边沿。

## 非目标

- 不实现鼠标移动/滚轮映射（官方 KeyboardMouseInjectRunner 的摇杆/体感转鼠标部分
  与六键无关，体感瞄准已有 ADR-027 softmap 路线）。
- 不装 FeizVKB/VMO 内核驱动，不做驱动级注入。
- 不做 attach 自动改固件表（见决策 5）。
- 不动 ADR-019 testmode 端点与其备份/还原语义。

## 影响

- `rawstream.RawStreamHub.demands` 增加固定键 `extkeymap`（watchdog 语义不变）。
- `softmap.VK` 扩表（F1-F12/方向键/ESC/ENTER 等，纯增量）。
- 新端点 GET/POST `/api/extkeys/mapping`；PadTest 拓展键卡加映射 UI。
