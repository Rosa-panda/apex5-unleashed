# 隐藏功能挖掘清单（2026-09-20 调研，未立项）

> 目的：盘点八爪鱼5 官方未释放/社区少有人知的能力，作为后续立项池。
> 三路情报：① openflydigi（工作区本地，MIT/CC0，真机验证文档）② 空间站反编译
> `spacestation\decomp\`（controller-sdk 命令工厂 + biz/runner 业务层）③ 联网社区
> （知乎/B站/飞智帮助中心/官方 FAQ）。**本文只是清单，动代码前须先写 ADR。**

## A. 设备级设置（cmd 3 读块 + cmd 19/20-23/29 写，报文极简即发即效）

cmd 3 一次读回全部 supported/enabled 双位图 + 数值（openflydigi 真机布局）：

| cmd / 子项 | 功能 | 备注 |
|---|---|---|
| 3 | 读全部功能位图+数值 | `data[5..12]`：10 项开关 + 睡眠/回报率/精度/灵敏度 |
| 19 sub1 | QuickSwitch 快切配置 | 手柄端组合键切档案 |
| 19 sub5/6/7 | 摇杆消抖 / 自动校准 / 回弹算法 | 消抖关=更跟手但抖+自动校准失效 |
| 19 sub8/9 | 状态栏常亮 / 屏幕开关 | 9 已实现（屏幕页） |
| 19 sub3/10 | 体感去抖 / 音频开关 | **k5 实测均 unsupported**（cmd3 位图判死） |
| 20 | 回报率 {1000=1,500=2,250=4,125=8} | 读回值 0=None 语义未知，勿瞎写 |
| 21 | 摇杆精度（枚举乱序：2=10bit！） | 实测 10↔12bit 分辨率差 3 倍 |
| 22 | 摇杆灵敏度 7 档（14..20） | |
| 23 | 睡眠时间（分钟，0=永不） | |
| 29 | 软重启 | openflydigi 未敢真机发过 |
| 25 / 27 | 一键禁用宏映射 / 蓝牙模式切换 | 反编译发现 |

## B. Profile blob 内的固件原生功能（840B，走已趟平的 161-166 通路）

| 偏移 | 功能 | 说明 |
|---|---|---|
| 137..145 + 830 | **体感映射**（陀螺→摇杆/按键 + 平滑曲线） | 官方「体感瞄准」本体；反编译另有 MotionMapTypeMouse |
| 109..123 | **摇杆响应曲线**（7 控制点，出厂=直线） | 死区/灵敏度曲线全在这里 |
| 802..814 | 摇杆 9 点扩展曲线 + isRound 圆/矩形边界 | |
| 123..137 | **扳机行程曲线** | |
| 770..790 | 每档案名称（20B UTF-16LE） | 备份文件里躺着没用 |
| 154..183 | 扳机马达齿轮（Vader 系；k5 有力反馈扳机，意义存疑） | |
| **档案 4..7** | **Switch 第二银行**：cmd 171=带目的地的 166 | 真机验证：Switch 下 enumerates 成 Pro Controller 057e:2009，可给背键补 Pro 缺的键；读路径 alias 只能写 |

## C. 校准 / 工厂 / 测试族（241-253 + 175/240）

| cmd | 功能 | 风险 |
|---|---|---|
| 240 | ADC 摇杆校准（start=1/2） | 漂移救星，报文已知 |
| 19 sub6 | 自动校准开关 | 低 |
| 175 | 恢复默认档案 | ⚠ openflydigi 真机实测：**忽略 cfgId，全部 4 档案+名称重置**，10s flash 超时 |
| 253 | TestRecoverFactory 整机恢复出厂（仅 NewXInput 实现） | 反编译发现，未验证 |
| 246 | TestJoystick 摇杆原始采样流 | 诊断工具素材 |
| 241/244/245 | 指示灯 / RF丢包 / RGB 测试 | 245 我们实测 ACK 但灯不变（需诊断态） |
| 247 | 扳机效果测试 | |

## D. 代理权 / 共存仲裁（对我们独有价值）

- **cmd 28 AcquireController**：官方协作锁，`[4]=23,[5]=acquire,[6..25]` 20 字节 ASCII tag——**Steam 每 30s 就用它**。我们发 acquire 可让官方/Steam 让权，比现在的「命令铁证+15s 收回」更文明。
- **cmd 16 `control_by` 20 字节标签**：手柄自己招供谁在驱动（Steam 接管时自填 "SDL"）——代理权归因可从「扫描进程+抓包推断」升级为「设备直读」。
- cmd 17 fifth flag = thirdPartyControl（「允许第三方接管」开关本体）。

## E. 7878 协议已定义但官方没接的指令类型

`AdapterTriggerResource.cs` 定义 7 种 InstructionType，官方服务**只处理 type1 TriggerUpdate**，其余静默丢弃：**RGBUpdate / PlayerLED / PlayerLEDNewRevision / MicLED / TriggerThreshold**。我们 ingress 已收全包——把这几类翻译成自家灯表/扳机命令 = DSX 社区 mod 生态白送灯效联动。

## F. 体感转鼠标（PC 全游戏陀螺瞄准）

- 0xEF 流格式（openflydigi 真机）：report id 0x04，**gyro@18/20/22、accel@24/26/28、摇杆@4/6/8/10**，accel scale≈2.441，gyro scale 可调。
- **官方陀螺→鼠标完整算法（探员A 反编译实锤）**：GyroScale=0.06103702（=1000/16384，原始值→mdps）；
  死区 |gyro原始|<8；加速度曲线 阈值 2.0、指数 1.3（`2+2*((v-2)/2)^1.3`）；灵敏度换算 Sensitivity/50；
  鼠标位移 = 取负后 yaw/pitch × sens。k5 **FW≥7.0.3.0 走 6DoF 融合路径**，否则老路径 gyro*sens*0.1。
  摇杆→鼠标 `(X-center)*sens >> 16`；摇杆→键盘 = 8 方向；滚轮 ±10。
- ⚠ **勘误（探员A）**：官方键鼠注入**不走手柄 interface 1.1**——那是手柄→PC 的键鼠报文上报通道
  （cmd 17 keyboard/mouse 开关控制）。官方注入靠 PC 侧内核驱动 FeizVKB64.sys/FeizVMO64.sys。
  我们用 SendInput 即可，无需驱动。
- 我们已在收这条流（extkey 位图同源），软件侧 SendInput 即可做全游戏陀螺瞄准；固件侧走 B-体感映射。

## G. 零散有价值的命令

| cmd | 功能 | 备注 |
|---|---|---|
| 2 / 24 | 读 / 写整机昵称（1-26B UTF-8） | 多设备区分 |
| 32 | 读当前生效 profile id | 账本核对 |
| 48 | ExtraInfo：7 颗芯片固件版本 + 屏设置 | 信息面板 |
| 232 | EnableDS5Data 开 DS5 数据格式 | **PS5 模式线索，官方按力反馈门控；Windows 效果未知，高危实验** |
| 31 | HID 通道进固件升级（可指 ChipModule） | 已有串口 0x1F，备选二路 |
| 18 | VibrationType 0=握把 2=扳机振动 | 扳机马达独立驱动（k5 待验证） |
| 20字节 cmd48 子命令族 | XInput 方言：force trigger/test vib/升级模式 | 走 MI_00 接口 |

## H. UI 功能面挖掘（探员B，2026-09-20）

来源：`spacestation\asar\.vite\`（Electron 主进程 main.js + 12 语言 locale + 渲染层按页 chunk）
+ `decomp\shared-proto\`（protobuf 生成类全集）。

### H1. 首次浮出水面的完整功能模型（protobuf 字段级）

| 模型 | 字段 | 意义 |
|---|---|---|
| MotionConfigBean | UseMode(FPS/Racer) + MappingType(**Off/左摇杆/右摇杆/鼠标**) | 体感双模式；射击=右摇杆、赛车=左摇杆 |
| MotionMapTypeJoystick | EnableType(**Click/Press**)、EnableKey、Sensitivity、DeadZone、Smoothness | 官方体感也有"按住激活"形态（与我们设计吻合✓） |
| MotionMapTypeMouse | EnableType、EnableKey、SensitivityX/Y | 陀螺→鼠标 XY 独立灵敏度 |
| MotionSmoothnessConfig | Zero/Point1/Point2/End 4 点平滑曲线 | |
| JoystickConfigBean | MapType(**摇杆/键盘/鼠标/十字键**) | 摇杆可整体映射成别的东西 |
| JoystickMapTypeJoystick | CircularityType(圆/矩形)、**Center(中心死区+补偿)**、**Edge(边缘死区+补偿)**、SensitivityConfig | |
| JoystickSensitivityConfig | Type(Default/Quick/Slow/**Custom**) + Point1/Point2/Points[] | 自定义曲线多点 |
| JoystickMapTypeMouse/Keyboard | DeadZone、SensitivityX/Y / Direction(**4向/8向**)、每方向 MapKeyId | 摇杆→鼠标、摇杆→键盘(8向) |
| KeyConfigBean | MapType: Key / **Continuous(连发: EnableType+Frequency)** / Macro / MultiFunction | **固件级连发 Turbo，每键可设** |
| TriggerConfigBean | Zero/End、TriggerVibrationConfigBean(**Linear+Micro 双通道**)、Point1/Point2 | |
| VibrationConfigBean | 左右握把各 Enable/**Min/Max/Scale** | 「50% 可模拟 xbox」校准线 |
| LedConfigBean | GripSync(震动同步灯效)、分灯组 LedGroup、FramedLedColor 逐帧 | |
| ControllerMappingConfigBean:72 | **`Lunpan`(轮盘) 字段 14** | ⚠ 疑似未曝光的转盘/拨轮配置，待逆向 MappingConfigParser |

### H2. fcs.sock 命名管道 RPC 全家福（除 Mod/扳机外官方还跑了这些）

配置 CRUD 4097-4127；分享码 4122-4124+4133-4134（板载/本地/宏配置生成分享码互相导入）；
屏幕 4144-4148；震动测试 4176-4178；系统设置 4179-4191（回报率/休眠/精度/灵敏度/防抖/
自动校准/回弹/快切/昵称/音频/底座智能停）；散热器 28673-28695；底座 24577-24581；
出厂诊断 65520-65529；**键鼠注入 = EnableRawData(12) + 服务端 KeyboardMouseInjectRunner**
（陀螺→鼠标 :463、摇杆→鼠标 :563、InjectKeyboardSimulator :279，配 driver\FeizVkeyMouHelper）；
虚拟手柄 = EnableXinput(11) + XInputHelper（正是 vibfix 修的抢 0 号槽来源）；
AcquireController/CheckThirdPartyAcquiredController 17/18。

### H3. UI 有而我们没有 Top 10（探员B 按价值排序）

1. 体感映射（参数模型全拿到，见 H1）
2. **摇杆→鼠标/键盘映射**（官方由服务端 SendInput 注入；我们自研 SendInput 替代）
3. 摇杆高级设置全家（防抖/回弹/自动校准/精度/中心灵敏度）
4. 摇杆死区/补偿/自定义曲线/圆率
5. 校准+画圆误差/回报率/丢包诊断（AdcCalibration、RollingRateChecker.cs、TestDongleLosses）
6. **连发 Turbo**（KeyMapTypeContinuous，固件级零注入成本，blob 键表 MapType 即达）
7. **4 板载配置槽 + fn+A/B/X/Y 快切**（官方 locale 实锤快切键位；cmd 19 sub1 QuickSwitch）
8. **配置分享码**（社区生态入口，我们路线图本来就有"社区预设分享"）
9. 系统设置：回报率/休眠/音频/昵称/第三方接管**放行**开关（我们只做检测，官方可放行）
10. 握把震动 min/max/scale + GripSync 震动同步灯效

### H4. 新设备类别（有硬件再做）

- **CD2 充电底座**（37d7:6001）：七种 LED 高级模式、逐帧 DIY 编辑器、灯光同步、充电动画、智能启停
- **BS2/BS3 散热器**：四档转速/超频/智能变频/温度-转速曲线/PD 功率解锁/CPU·GPU 温度监控
- **FS68 磁轴键盘**：SOCD/RS/MT/DKS 4 段键程/RapidTrigger（ShadowKeyboardPage 整套 UI）——非手柄，N/A
- 账号/积分商城/NPS：云端运营，N/A 不做

### H5. 其他零碎

- 官方警告「体感映射导致回报率降低」——体感开时回报率会掉，设计 UI 时要提示
- 屏幕：状态栏常亮（cmd 19 sub8）/关屏（sub9 已实现）；GIF 帧范围裁剪；官方素材库/社群投稿
- 固件**七模块**：主控/接收器/RF(星闪)/SI/扳机/屏幕/ADC，各有版本，支持 rollback（cmd 48 可读全版本）
- 宏录制还能在**手柄上直接录**：fn+拓展键 1.5s（固件自带，无需软件！）
- 连发也能手柄上直接设/清（rapid_fire_* locale）

## I. 全命令号 Census（探员A，2026-09-20）

### I1. 结构性认知（重要）

- controller-sdk 每个 CommandFactory 内含 2-3 个协议变体类（NewXInput/XInput/DInput），
  **只有 NewXInput 对 k5 有效**；此前清单里 48/51/52/80-82/232/233/238/240-247 大多是
  XInput/DInput 变体号，NX 重号但语义可能不同（如 NX 240=ADC 校准、NX 242=测屏）。
- **空号段确认无工厂**：5,6,8-15,26,30,33-47,49,50,53-79,88-160,176-207,212-223,231,
  234,236-239,243,248-252,255 在 NX 侧全部无实现——HID 命令面已穷尽，没有隐藏号段了。
- K6 扳机 83-87 死因定案：`IsK6TriggerProtocolSupported` 门控 DeviceCode=="k6"（ControllerSdk.cs:680），
  k5 直接拒绝。83-86 帧格式已完整逆向存档（波形/强度映射，APEX6/未来固件可能复用）。
- ⚠ cmd 172/173/174 NX 工厂存在（宏库读写），**但我们真机实测 k5 恒回 total=4 游标不推进
  （ADR-021），与 openflydigi "v3.2 通路" 结论一致——工厂在、固件不配合，维持判死**。

### I2. 新拿到的权威报文布局

| 命令 | 布局 | 用途 |
|---|---|---|
| cmd 3 ACK | data[5] usable 位图（bit0 快切/1 XboxHome/2 体感去抖/3 映射开关/4 摇杆防抖/5 自动校准/6 回中/7 状态栏）、[6] enabled 同布局、[7]/[8] 关屏+Audio、[9..12] 休眠/回报率/精度/灵敏度 | 能力探测唯一真相 |
| cmd 16 ACK | [5]XInputEnabled [6]PrivateData [7]Keyboard [8]Mouse [9]第三方控制 Enabled **[10..30)=ASCII 占用方标签** | 代理权实名（control_by 在 [10..30)） |
| cmd 17 | 5 个开关字节，**0xFF=保持不变** | 精确改一位不冲其他位 |
| cmd 7 ACK | 判据 data[3]==1 && data[4]==0；ProductId==0x2401 → 新架构；超时回退 161+2 | 协议探测权威实现 |
| cmd 28 | [4]=23,[5]=acquire,[6..25] 20B ASCII tag | 仲裁协议（Steam 在用） |

### I3. 虚拟 DS5 官方通路（PS5 模式真相）

`EnablePs5` 开启后把 0xEF 流 `FormateDSModeData` 经 **PS5Driver.dll（XGIP）** 送成 DS5 设备
给 PC 游戏（ControllerRepository.cs:2444-2457）——官方的"虚拟 DualSense"是**内核驱动级**，
k5 门控 FW≥7.0.3.0。我们的 cmd 232 EnableDS5Data 是这条路的 HID 侧开关。ADR-020 已裁决
桥接路线封存，此通路仅作记录，不重启。

### I4. 云/网络定案

biz 服务层**零账号/云代码**；分享码 IPC 只是字节落盘/取出，上传下载全在 Electron UI。
云配置协议无服务端可逆，价值低。

### I5. 外设 SDK（未反编译，下一步候选）

CoolerSdk.dll / ChargerSdk.dll 独立编译未反编译；biz 层已暴露功能面（散热器 bs2/bs2pro/
bs3/bs3pro 四型、智能温控服务 IntelligientCoolingService；底座 LED/充电动画/智能启停）。
HID 层命令格式要逆这两个 DLL 才能拿到。

## 判死/勿碰（已有实锤，勿重踩）

cmd 87（K6 X-Haptics，k5 ACK-but-ignore）；cmd 172-174（v3.2 宏库，k5 走 blob 宏页）；
cmd 208-211（k5 屏幕走串口 OTA）；cmd 242/0xF5；19 sub3/10（k5 硬件不支持）。

## 立项优先级建议（好玩度 × 可行性）

| # | 功能 | 来源 | 可行性 |
|---|---|---|---|
| 1 | 体感瞄准（陀螺→鼠标 + 固件体感映射） | F + B | 高（流已在收，官方参数现成） |
| 2 | 摇杆/扳机曲线编辑器 | B | 高（42 包写通路现成，零风险） |
| 3 | 设备设置页（A 全节 + cmd 2/24/32/48） | A/G | 高（报文简单，cmd3 位图自判能力） |
| 4 | cmd 28+16 共存仲裁升级 | D | 高，独有卖点 |
| 5 | 7878 灯效指令翻译 | E | 中（翻译工作量） |
| 6 | 摇杆校准/诊断（240/246+死区可视化） | C | 中 |
| 7 | Switch 第二银行写入 | B | 中（受众窄但独一份） |
| 8 | 恢复出厂/重置入口（175/253） | C | 中（高风险操作需红线闸门） |
| 9 | DS5 数据格式实验（232） | G | 低（未知数大，封实验区） |

## 来源登记

- openflydigi：README / PROGRESS / docs\device-settings.md / findings-profile-blob.md / findings-steam.md / findings-haptics.md / findings-games.md / findings-other-devices.md（MIT/CC0，已记 REFERENCES.md 致谢体系）
- 空间站反编译：`spacestation\decomp\controller-sdk\`（command 工厂）、`decomp\biz\`（KeyboardMouseInjectRunner）、`decomp\runner\`（AdapterTriggerResource）
- 社区：飞智帮助中心快捷键页、官方 FAQ（SELECT+START+↑ 硬件校准组合键）、知乎深度评测、B站调优视频、r/GyroGaming、padctl、flydigi-space-station-mac
