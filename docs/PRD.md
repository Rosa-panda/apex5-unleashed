# PRD · Apex5 Unleashed 产品需求文档

> **文档性质：存量补录（retroactive PRD）**。本项目已开发至 v0.3.2 并实跑可用，本文不是从零立项，
> 而是把 README / ADR / TECH-SPEC / PROTOCOL / 风险登记册与实际代码中**已经存在的能力**固化为一份
> 正式需求基线，供架构师做规范化改造时对照。
>
> - 版本基线：**v0.3.2**（`VERSION` 文件为唯一真相源）
> - 事实来源：`README.md`、`docs/TECH-SPEC.md`、`docs/PROTOCOL.md`、`docs/adr/ADR-001~034`、
>   `docs/TEST-PLAN.md`、`docs/RISK-REGISTER.md`、`docs/RESEARCH-HIDDEN-FEATURES.md`、
>   `backend/app/**`、`frontend/src/pages/**`
> - 标注约定：✅ = 已实现并可用；⏳ = 部分实现；⬜ = 待办（未实现）
> - 本文**不立项新功能**。所有新增/变更需求仍须按 ADR-012 纪律先走 ADR。

---

## 1. 产品定义

### 1.1 一句话定位

> **开源的飞智八爪鱼5（Apex 5）PC 工具箱 —— 把官方没开放的扳机、灯光、屏幕、宏、体感参数面，做成可视化实时调校，并在进游戏时自动生效。**

非官方产品，与飞智无关。基于对飞智私有 HID 协议的实机逆向（`docs/PROTOCOL.md`）构建，GPLv3 许可。

### 1.2 目标用户

| 用户群 | 画像 | 核心诉求 | 主用功能面 |
|---|---|---|---|
| **A. 硬核 PC 玩家（主目标）** | 拥有 Apex 5、在 PC 上玩 FPS / 赛车 / 动作大作，对手感和"逐游戏适配"有执念 | 扳机手感自己说了算；进游戏不用手动切配置 | 扳机实验室、游戏库/预设库、板载宏 |
| **B. 模拟器 / 体感玩家** | 在 Yuzu / Cemu / Dolphin / PCSX2 上玩，需要陀螺体感 | 手柄陀螺能喂给模拟器（DSU/Cemuhook）；PC 全游戏陀螺瞄准 | 体感中心（DSU 桥、陀螺瞄准、迷宫试玩场） |
| **C. 折腾党 / 社区贡献者** | 愿意录档案、导参数、试实验功能、给别人分享配置 | 自定义入口 + 可流通的配置载体 | 自定义档案、官方包导入、分享码、测试区 |
| **D. 维护者 / 开发者** | 巴士因子 = 1（R8），全球测试环境只有 1 个手柄（R4） | 无硬件也能开发、验证、回归 | Mock 全链路、事件日志、ADR、trace 回放（待办） |

### 1.3 与官方「飞智空间站」的差异化（只做官方架构做不了的事）

> 立身之本（ADR-003）：**不做官方功能平替**。官方适配 = 静态参数包 + 震动转发，封闭、无事件级开放接口、
> 无社区配置格式。我们只补官方结构性做不到的部分。

| 维度 | 官方飞智空间站 | Apex5 Unleashed |
|---|---|---|
| 扳机调参 | 93 款静态参数包，玩家不可调 | 六种自适应扳机模式**全参数实时调校**，preview 调参即生效（ADR-003 / TECH-SPEC §4） |
| 适配覆盖面 | 93 款官方手工调参，不含 DualSense 原生游戏 | ~280 款档案：官方调参 34 条 + ASB「DS 原生」181 条（题材 k-NN 自动生成）+ 题材适配 + Mod 条目（ADR-017/022/024） |
| 事件级扳机 | 仅自家 Mod 生态可用 | 官方 Mod 管家 + DSX UDP ingress，兼容 DSX 社区 mod 生态；**并把官方静默丢弃的 DSX 指令（RGBUpdate/PlayerLED 等）翻译出来**（ADR-025 / RESEARCH §E） |
| 共存可观测性 | 无（自家虚拟手柄抢占 XInput 0 号槽却不明示） | 代理权总线级铁证检测 + 进程归因 + 震动抢占一键修复（ADR-006/013、vibfix） |
| 配置生态 | 封闭 | 开放格式 `apex5-game-config/1`（ADR-015）+ 纯 JSON 文件 PR 即贡献 |
| 模拟器体感 | 不覆盖 | DSU/Cemuhook 桥（ADR-027/028，真机 97Hz 实测） |
| 协议与参数面 | 不开放 | 全开放：拓展键、宏页、灯表、屏幕 OTA、设备设置、共存仲裁（RESEARCH §A~§G） |

### 1.4 产品目标（三条正交）

| 目标 | 定义 | 可衡量判据 |
|---|---|---|
| **G1 · 手感可控** | 把官方未开放的扳机 / 灯光 / 屏幕 / 宏 / 体感参数面，做成可视化实时调校并能写进固件驻留 | 六模式全参数可调且 preview 不落账本；宏关软件仍触发；灯效/屏幕写入后设备断电仍驻留 |
| **G2 · 进游戏零操作** | 前台进程识别 + 五档适配 + Mod 事件转译，让玩家不再手动切配置 | 切到已适配游戏 ≤1 个切换周期内自动套用并给出可见提示；通用震动联动兜底任意游戏 |
| **G3 · 可信可观测** | 锁存账本保证「软件所见 = 手柄真实状态」；硬件写有确认闸门、有备份、有账本 | 重启后账本重读 = 手柄实际（TEST-PLAN #4）；代理权检测 ≤5s（#5）；退出无残留效果（#8） |

### 1.5 能力边界（诚实声明，必须随产品传播）

DualSense 原生游戏的**事件级**自适应扳机效果，是游戏运行时发给 DualSense 硬件的报告流——
手柄本身不是 DualSense 时这些数据根本不存在，**无法凭空还原**。我们转译的是其**体验**
（逐游戏震动参数包，ADR-024），而非配置本身；事件级效果请走官方 Mod 管家路线（ADR-025）。

---

## 2. 用户故事

### A. 硬核 PC 玩家

| # | 用户故事 |
|---|---|
| US-1 | 作为 **FPS 玩家**，我希望在扳机实验室里逐参数拖动六种自适应扳机模式并即时试手感，以便找到最适合我这把枪的扳机曲线，而不是在官方给的静态参数包里二选一。 |
| US-2 | 作为 **玩家**，我希望把调好的手感存成预设并能导出/导入，以便重装系统或换机器时不用从头调一遍。 |
| US-3 | 作为 **玩家**，我希望切进游戏时工具自动识别前台进程并套上对应适配档案，以便我不用每次进游戏前先打开软件点一下。 |
| US-4 | 作为 **长尾游戏玩家**，我希望即使游戏不在官方适配名单里，也有「题材适配 / 通用震动联动」兜底，以便我玩冷门游戏时手柄不至于毫无反馈。 |
| US-5 | 作为 **动作游戏玩家**，我希望把连招录成板载宏写进手柄固件，以便关掉电脑上的软件、甚至在别的地方用手柄时宏照样触发。 |
| US-6 | 作为 **玩家**，我希望六个拓展键在手柄图上按哪个亮哪个、且默认就是独立的六个键，以便我确认自己按的是 M3 而不是被别名掉的 LB。 |
| US-7 | 作为 **玩家**，我希望一键下载安装官方 CDN 的游戏 Mod 并让事件级扳机效果实时转到手柄，以便玩到官方生态里的原生适配。 |

### B. 模拟器 / 体感玩家

| # | 用户故事 |
|---|---|
| US-8 | 作为 **模拟器玩家**，我希望手柄陀螺能通过 DSU/Cemuhook 协议喂给 Yuzu / Cemu / Dolphin / PCSX2，以便我在模拟器里直接用体感瞄准。 |
| US-9 | 作为 **PC 体感玩家**，我希望陀螺能映射成鼠标输入（软件层）或摇杆/按键（固件层），以便没有原生体感支持的游戏也能用体感。 |
| US-10 | 作为 **体感新手**，我希望有一个迷宫试玩场可以练手感，以便在调参时能立刻看到体感输入的实时反馈。 |

### C. 折腾党 / 社区贡献者

| # | 用户故事 |
|---|---|
| US-11 | 作为 **折腾党**，我希望一键导入官方适配包、并能为特殊版本的游戏手动定位 exe，以便小众/修改版游戏也能被正确识别。 |
| US-12 | 作为 **折腾党**，我希望在测试区里试用还没转正的实验功能（连发、曲线编辑、设备设置、摇杆体检、4 配置槽、分享码……），以便我先玩到再说，同时知道这些功能还没承诺稳定。 |
| US-13 | 作为 **社区贡献者**，我希望配置能以纯文本（JSON / 分享码）流通，以便我把自己的调参成果发给别人，而不是截图让人手抄。 |

### D. 维护者 / 开发者

| # | 用户故事 |
|---|---|
| US-14 | 作为 **维护者**，我希望在没有手柄接上的时候软件自动进入 Mock 模式跑通全链路，以便我在任何机器上都能开发和做回归。 |
| US-15 | 作为 **维护者**，我希望每一条下行命令都有「时间 / 来源 / hex / 结果」的事件日志，以便线上出问题时我能还原当时到底发了什么。 |
| US-16 | 作为 **用户**，我希望所有写硬件的操作都有确认闸门和备份，以便我手滑点了重置/烧写也不会把配置搞没。 |

---

## 3. 需求池

> 优先级定义：**P0** = 产品的骨架，缺一项产品不成立；**P1** = 重要增强，缺失影响体验或可信度；
> **P2** = 锦上添花 / 生态项，可延后。

### 3.1 P0 · 核心能力（必须存在）

| ID | 需求 | 状态 | 实现模块 / 接口 | 依据 |
|---|---|---|---|---|
| P0-1 | 协议引擎与设备生命周期管理：单 HID 读写线程、命令队列超时重试、热插拔重连、启动卫生检查 panic | ✅ | `engine.py`、`transport.py` | ADR-010/012、TECH-SPEC §2/§3 |
| P0-2 | 扳机实验室：六种自适应扳机模式（Normal/Race/Sniper/Recoil/Lock/Vibration）全参数实时调校，preview 不落账本、apply 才落 | ✅ | `TriggerLab.tsx`、`POST /api/trigger` | ADR-003、TECH-SPEC §3/§4 |
| P0-3 | 预设库：预设 CRUD、导入导出、应用为事务（失败回滚 Normal 基线） | ✅ | `presets.py`、`routers/presets.py` | TECH-SPEC §4 |
| P0-4 | 游戏库 + 前台进程自动切换（SetWinEventHook，失败退 1Hz 轮询） | ✅ | `gameprofiles.py`、`routers/games.py` | ADR-008/014 |
| P0-5 | 五档适配分级：官方适配 / DS转官 / DS转官·通用 / 题材适配 / Mod 条目 | ✅ | `gameprofiles.py`、`GameLibrary.tsx` | ADR-017/022/024 |
| P0-6 | 官方 Mod 管家：CDN 下载、安装、启用、前台驱动拉起、退出收尾、运行态展示 | ✅ | `modmgr.py`、`/api/mods*` | ADR-025 |
| P0-7 | DSX UDP ingress：7878（占用退 8787）收事件流，飞智包直通 cmd51 + DSX 社区包近似翻译 | ✅ | `dsxingress.py` | ADR-009/025 |
| P0-8 | 板载宏：写固件（≤5 条 / 单条 ≤64 步 / 全页 ≤128 步 / 10ms tick）、录制、单次·按住循环·点击循环、循环间隔、复制、JSON 导入导出、整机备份恢复 | ✅ | `macro.py`、`routers/macro.py`、`Macros.tsx` | ADR-021/032 |
| P0-9 | 拓展键：一等键语义（默认全 255 透传）、0xEF 位图实时回显（按 M 键图上 M 键亮）、双通道映射（固件键表 / 软件 SendInput 注入） | ✅ | `extkeys.py`、`extkeymap.py`、`PadTest.tsx` | ADR-016/019/030/031 |
| P0-10 | 灯光工坊：灯效库 + 速度/亮度调节（真机标定）、进页自动还原当前灯效（含外来灯效逐帧回放）、一键关灯、灯表备份恢复 | ✅ | `protocol.led_frames_*`、`routers/led.py`、`Lights.tsx` | ADR-018/033/034 |
| P0-11 | 屏幕：自定义 GIF 写入手柄屏幕（自动抽帧保原速、串口 OTA 烧写）+ 红线确认闸门 | ✅ | `screenpack.py`、`screenota.py`、`routers/screen.py` | ADR-018 |
| P0-12 | 体感中心：体感总闸（状态持久化）+ 陀螺瞄准（软件映射）+ 固件陀螺映射 + DSU/Cemuhook 桥 + 迷宫试玩场 | ✅ | `motionmaster.py`、`softmap.py`、`dsu.py`、`maze.py`、`Motion.tsx` | ADR-027/028 |
| P0-13 | 状态与可观测性：电量（含充电态）、代理权检测（总线铁证 + 进程归因）、锁存账本、命令级事件日志、WS 快照 + 逐条事件推送（体感帧 30Hz 节流） | ✅ | `routers/system.py`、`wsbus.py`、`routers/ws.py` | ADR-006/013、TECH-SPEC §5/§9 |
| P0-14 | 硬件写安全网：确认闸门 + 备份先行 + 全页常驻「手柄复位（panic）」 | ✅ | `routers/screen.py`、`routers/explab.py`、`App.tsx` | ADR-010/018/032 |

### 3.2 P1 · 重要增强

| ID | 需求 | 状态 | 实现模块 / 接口 | 依据 |
|---|---|---|---|---|
| P1-1 | 通用震动联动（任意游戏兜底，cmd 0x52 固件路由） | ✅ | `POST /api/vib/universal` | ADR-017/024 |
| P1-2 | 官方适配包一键导入（vib 字段 → 通用震动联动） | ✅ | `officialimport.py`、`/api/games/import-official` | ADR-017 |
| P1-3 | 自定义 exe 定位（特殊版本/修改版游戏） | ✅ | `POST /api/games/{gid}/exe` | ADR-017 |
| P1-4 | 游戏震动修复：检测飞智虚拟手柄抢占 XInput 0 号槽，临时修复（退出自还原）/ 永久修复，全程账本留痕 | ✅ | `vibfix.py`、`routers/settings.py` | README「游戏震动修复」 |
| P1-5 | 灯效参数化模板：comet/rain/chase/pulse/duosweep 的方向、拖尾、倍速、圆心、融合旋钮 | ✅ | `protocol.py` 生成器 kwargs、`Lights.tsx` | ADR-034 |
| P1-6 | 帧画布（辅路径）：12 灯 × 10 帧网格直写 + localStorage 本地保存 | ✅ | `POST /api/led/apply_frames` | ADR-033 修订4 / ADR-034 |
| P1-7 | 拓展键↔宏的键表单一所有权：宏绑定 > 映射配置；宏占用键在映射卡锁定并标注，删宏后自动回落 | ✅ | `macro.write`、`extkeys.set_targets` | ADR-032 |
| P1-8 | 电量心跳的静默停发（手柄静默时不发心跳，避免固件把主机 report 当活动 → 永不休眠） | ✅ | `main.py#monitor_loop` | 2026-09-22 用户实锤 |
| P1-9 | 桌面壳与运维：pywebview 窗口 + 托盘三态 + 单实例唤起 + 关窗缩托盘 + 开机自启 | ✅ | `main.py`、`tray.py`、`/api/settings/autostart` | ADR-004/005 |
| P1-10 | Mock 设备层 + 自动化测试资产：**35 个 pytest 用例**（`test_protocol_units.py` 20 + `test_dsx_mod.py` 9 + `test_rawstream.py` 6）+ **11 个脚本式自检**（`test_reclaim` / `test_led` / `test_macro` 等，模块级 assert，需 `python tools/run_script_tests.py` 或 `python test_x.py` 单独跑）+ `smoke_test.py` 全链路冒烟（入口 `python tools/run_smoke.py`）+ 前端 `npm run build` | ✅ | `transport.MockPad`、`backend/conftest.py`、`backend/test_*.py`、`smoke_test.py`、`tools/run_smoke.py` | ADR-011、TEST-PLAN |
| P1-11 | 测试区（实验功能孵化区）：15 项注册表驱动卡片 + 判定账本（好用/不好用/待测），真机验证后才转正 | ✅ | `explab.py`、`/api/exp/*`、`ExpLab.tsx` | ADR-026/027 |
| P1-12 | 分享码本地编解码（预设 / 档案 / 宏 → 字符串，无云端） | ✅ | `sharecode.py`、`/api/exp/sharecode/*` | RESEARCH §H2/H3-8 |
| P1-13 | 灯表容量约束的产品化处理：全量灯效压到 ≤10 帧，或写入前对超限帧表显式告警 | ⬜ 待办 | `protocol.py`、`routers/led.py` | ADR-033 修订 5（固件槽位 = 10 帧，超限被静默截断，自校验不报错） |
| P1-14 | HID 总线满负荷上限压测（探针压测子命令，明确 32B 中断端点吞吐天花板） | ⬜ 待办 | — | RISK-REGISTER R6 |

> **P1-10 补充说明（2026-09 架构核对实跑结果）**：测试资产目前是**两套形态并存**——
> ① `test_dsx_mod.py`（9）、`test_rawstream.py`（6）是标准 pytest 形态，`pytest` 共收集 **15 个 item**，全过；
> ② 其余 11 个 `test_*.py` 是**脚本式自检**（模块级 `assert`，import 即执行，不计入 pytest item，需 `python test_x.py` 单独跑）；
> ③ `smoke_test.py` 是 HTTP 全链路冒烟（需后端在跑）——它在 import 期就发真实请求，
> **会把 `pytest` 收集阶段打成 collection error 并中断整轮**（后端未启动时 `ConnectionRefusedError`）。
> 该形态混用已派生 P2-9。
>
> **实测状态锚点（滚动更新 · 引用前必须自己重跑，勿信本页快照）**：
>
> | 核验项 | 状态 | 复跑命令 / 结果 |
> |---|---|---|
> | D8（`smoke_test.py` 打断 pytest 收集） | ✅ 已根治 | `backend/conftest.py` 已就位（`collect_ignore_glob=["smoke_test.py"]` + 绝对路径兜底，须留 `backend/` 不能放 `backend/app/`）；`python -m pytest backend -q` → **35 passed** |
> | pytest 用例数 | 15 → **35** | T04.1 的 `backend/test_protocol_units.py`（20 例）已落地：`test_protocol_units` 20 + `test_dsx_mod` 9 + `test_rawstream` 6 |
> | 冒烟入口 | ✅ 已落地 | `python tools/run_smoke.py`（自动起 Mock 服务 → 跑冒烟 → 收尾杀进程），已写入 README L48 |
> | 脚本式自检入口 | ✅ 已落地 | `python tools/run_script_tests.py` |
> | CI 门禁 | ✅ 已落地 | `.github/workflows/ci.yml` |
> | **上述全部是否已落库（commit）** | ❌ **否** | HEAD 仍为 `c94f092`；全部改动在未提交区（详见下方「落地 ≠ 落库」） |
>
> **⚠ 落地 ≠ 落库**：截至本锚点更新，T01–T04.1 的全部成果**尚未 commit**（`git status` 存在大量 M/D/??）。
> 仓库唯一的安全点是 HEAD `c94f092`（自带 tag `safe-20261006-pre-standardization` 与分支
> `backup/pre-standardization-20261006`）——**该安全点在本次改造之前**，改造所有增量都在它之后且未入库。
> 因此「功能已可用」与「成果已受版本控制保护」是两件事，验收与交接时必须分别确认。
>
> **更正记录（保持可追溯，不抹旧结论）**：本锚点经历了同日两次翻转——
> ① 早前核对时 `conftest.py` / `run_smoke.py` / `ci.yml` / `test_protocol_units.py` 均不存在，据此曾标注
> 「文档计划态」；② T03 落地后更正为「D8 已根治、15 passed」；③ T04.1 落地后再更正为当前的 35 passed。
> 每次翻都以「不可用 grep 模式覆盖不到的来路下否定结论」为教训，故本表只登记**可当场复跑的命令输出**。

### 3.3 P2 · 待办 / 生态项

| ID | 需求 | 状态 | 说明 | 依据 |
|---|---|---|---|---|
| P2-1 | **屏幕动画打磨**：GIF 帧范围裁剪、状态栏常亮开关、恢复出厂动画入口（当前挂在测试区 `screenplus`） | ⬜ 待办 | README「下一步」第 1 项 | ADR-018、explab #14 |
| P2-2 | **XGameMonitor 型 Mod 真机抽测**：官方 Mod 链路在真机上完成端到端收包验证 | ⬜ 待办 | README「下一步」第 2 项；ADR-025 明载「待真机实测收包」 | ADR-025 |
| P2-3 | **统一游戏配置格式 `apex5-game-config/1` 落地**：JSON Schema + `validate` + Mock 试驾 + 官方包/DSX 档案导入器（读旧写新） | ⬜ 待办 | README「下一步」第 3 项；事件段依赖 ingress（已由 ADR-025 落地，前置条件已满足） | ADR-015 |
| P2-4 | **分享码社区生态**：社区配置仓库 + 应用内「从仓库更新」 | ⬜ 待办 | README「下一步」第 4 项 | ADR-015、RESEARCH §H3-8 |
| P2-5 | 7878 端口与真 DSX 冲突的探测与退避提示 | ⬜ 待办 | 当前仅 7878→8787 退让，无占用方识别 | RISK-REGISTER R13 |
| P2-6 | Transport 层 trace 录制回放（真机命令-响应流 → CI 回放比对，硬件不在环） | ⬜ 待办 | 挂 Mock 同层（ADR-011 已预留） | TEST-PLAN「CI 策略」、R4 |
| P2-7 | 共存仲裁升级转正：cmd 28 `AcquireController` 主动让权 + cmd 16 `control_by` 20B 标签实名显示占用方 | ⬜ 待办 | 当前为测试区 `arbitration` 实验项 | RESEARCH §D |
| P2-8 | README 补写电机寿命 / 续航提示（持续高负载马达） | ⬜ 待办 | 低等级风险，一次性文案工作 | RISK-REGISTER R9 |
| P2-9 | 测试资产规范化：**按可离线程度分类处理** 11 个脚本式自检（离线可跑者 pytest 化纳 CI；依赖运行中服务/真机者保留手动脚本或加 marker 跳过），`smoke_test.py` 从默认收集路径排除（`conftest.py` 的 `collect_ignore_glob`，不改名） | ⏳ 部分（`smoke_test.py` 排除 **已落地**；11 个脚本的分类处理 —— 即产出「能否离线跑」分类表并据此分批纳管 —— **尚未开始**） | 现状见 P1-10 说明（含滚动实测锚点）；目标是 `pytest` 一条命令跑全集且不因后端未启动而中断。**注意：11 个脚本并不同质，不可一刀切**（分类原则见 §6 Q8） | ADR-011、TEST-PLAN「CI 策略」、R4/R8 |

---

## 4. UI / UX 设计约束

### 4.1 视觉基调

| 项 | 取值 / 规则 | 依据 |
|---|---|---|
| 风格 | 深色科技风 | ADR-004 |
| 背景 | `#0a0a0f` | ADR-004、TECH-SPEC §8 |
| 卡片 | `#12121a` | TECH-SPEC §8 |
| 边框 | `#1f1f2e` | TECH-SPEC §8 |
| 强调色 | `#22d3ee`（青） | ADR-004 |
| 危险色 | `#ef4444`（红） | TECH-SPEC §8 |
| 组件实现 | 以 Tailwind token 手工实现，不引 shadcn CLI | ADR-004 |
| 图标 | `lucide-react` | TECH-SPEC §8 |
| 语言 | 简体中文单语（多语言仅占位，未做） | TECH-SPEC §8 |

### 4.2 布局与框架

| 约束 | 说明 |
|---|---|
| 桌面端固定布局 | 窗口默认 1180×760，最小 960×620；**不做移动端/响应式适配** |
| 侧栏导航 | 固定 `w-52`，图标 + 文字，按「游戏与适配 / 手感工坊 / 个性装备 / 进阶」分组；总览独占首位 |
| 主区 | 内容容器 `max-w-[1120px]` 居中，单列滚动 |
| 常驻状态区 | 侧栏底部常驻「连接状态 + 电量 + 手柄复位」；顶栏常驻连接/电量/适配中/被接管状态胶囊——任何页面都能回答「连着没、电量多少、谁在管」 |
| 状态切换 | 无路由库，纯 state 导航（`App.tsx`） |
| 实时通道 | 单一 WS（`/ws`）：连接后先发一份快照，随后**事件逐条转发（不做合并/节流）**，保证命令 ACK 与设备事件实时可见；每客户端 `asyncio.Queue(maxsize=200)`，QueueFull 吞包（不阻塞引擎线程）；**体感帧例外**，由 `motionmaster.to_ws()` 做 **30Hz 节流**；断连显示全局横幅 + 自动重连 |
| 硬件依赖页 | 灯光 / 屏幕等真机依赖页经 `DeviceGate` 门控，离线不可操作 |
| 版本号 | 唯一真相源 = 仓库根 `VERSION`（经 `/api/version`），**禁止在界面硬编码** |

### 4.3 交互红线：写操作必须有确认闸门

> 硬件写入不可逆且可能残留效果（ADR-010 起源：强杀残留事故）。**任何写设备/改系统的操作都必须可确认、可回退、可追溯。**

| 操作 | 闸门形式 | 依据 |
|---|---|---|
| 屏幕 GIF 烧写 | `confirm=true` 必填，缺则后端直接拒绝；UI 明示风险与耗时 | ADR-018 红线 |
| 重置档案槽 / 整机重置 | 字符串双确认 `RESET` / `RESET-ALL` + **全量备份先行** | `routers/explab.py` |
| 板载宏写入 / 恢复 | 确认弹窗 + 备份；恢复限定宏区作用域（不整槽回写） | ADR-032 |
| 灯表写入 | 备份/还原入口常驻；进页自动还原当前灯效 | ADR-018 |
| 拓展键映射写固件 | 跳过宏占用键并在返回值回显 `skipped`，UI 标注「宏占用」 | ADR-032 |
| 虚拟手柄禁用（震动修复） | 必须过 Windows UAC 授权弹窗；默认**临时**修复且退出自还原；永久禁用只在设置页显式点击；全程账本留痕 | `vibfix.py` |
| 兜底 | 「手柄复位（panic）」按钮全页常驻，马达归零 + 双扳机回 Normal | `App.tsx` |

### 4.4 可观测性即产品功能（非调试设施）

- **锁存账本**：先记账再发送，UI 显示账本而非猜测值（TECH-SPEC §3）。
- **代理权状态签**：只做状态提示，不弹窗打断；飞智空间站 init 指纹命中时柔化为中性提示（ADR-023）。
- **事件日志**：每条下行命令四元组（时间 / 来源 / hex / 结果），UI 与 rotating 文件双通道（TECH-SPEC §9）。
- **测试区判定账本**：实验功能的好用/不好用判定持久化到 `exp_verdicts.json`，作为「是否转正」的证据链（ADR-026）。

---

## 5. 明确的非目标（边界条款）

> 本节用于防止范围蔓延（**RISK-REGISTER R12**：音频方案已砍又复活等）。新增需求若落入此表，须先出 ADR 推翻。

| # | 不做的事 | 依据 |
|---|---|---|
| N1 | **不做官方功能平替**：不重做键位映射、官方已有宏、陀螺转摇杆等官方已提供的常规能力 | ADR-003 |
| N2 | **不凭空还原 DualSense 事件级扳机效果**：手柄不是 DualSense 时数据源不存在，只转译体验 | ADR-024、README 能力边界 |
| N3 | **不做虚拟手柄 / 内核驱动 / 外部驱动依赖**：DS 虚拟手柄桥接路线已全量删除，代码零残留 | ADR-020 revB、R1/R7 已消除 |
| N4 | **不碰反作弊敏感能力**：不做游戏进程内存读写、不做注入、不做模拟输入到受保护游戏 | R1（合规，已消除） |
| N5 | **不支持八6 及其他手柄**：不追八6 X-Haptics（cmd 83-87 在八5 判死）；硬件支持面严守 Apex 5 / k5 | ADR-002、RESEARCH「判死/勿碰」 |
| N6 | **不做游戏音频触觉 / 音频分析**：混音后事件意图不可恢复 | ADR-001 |
| N7 | **不做云端账号 / 积分商城 / NPS 等运营功能**：无服务端，全本地 | RESEARCH §H4/§I4 |
| N8 | **不做规则积木式灯效编辑器**：易做成半吊子编程语言，待模板+参数与帧画布 A/B 后再评估 | ADR-034 非目标 |
| N9 | **不改宏页二进制布局、不突破固件上限（5 条/64 步/128 步/655s/10ms）、不做 PC 侧宏播放**：板载宏离手可用是卖点 | ADR-032 非目标 |
| N10 | **不做插件型 Mod（F4SE / ScriptHookV 等）**：v1 明确拒绝 | ADR-025 |
| N11 | **不做非手柄硬件**：CD2 充电底座、BS2/BS3 散热器、FS68 磁轴键盘，N/A | RESEARCH §H4 |
| N12 | **不做 cmd 232 EnableDS5Data（PS5 模式）实验**：官方走内核驱动级 PS5Driver.dll，Windows 效果未知、高危 | RESEARCH §I3、ADR-020 已裁决不重启桥接路线 |
| N13 | **不做已判死的命令通路**：cmd 87（K6 X-Haptics）、cmd 172-174（v3.2 宏库）、cmd 208-211（k5 屏幕走串口 OTA）、19 sub3/10（k5 硬件不支持） | RESEARCH「判死/勿碰」 |

---

## 6. 待确认问题（需拍板）

| # | 问题 | 背景 | 建议（待拍板） |
|---|---|---|---|
| Q1 | **v0.4 先做哪项？** README「下一步」四项：屏幕动画打磨 / XGameMonitor 型 Mod 真机抽测 / 统一游戏配置格式（ADR-015）/ 分享码社区生态 | 四项都是待办，资源只能先投一项 | 建议先做 **ADR-015 统一配置格式**：它是分享码生态与社区贡献路径的地基，另两项是局部打磨 |
| Q2 | **灯表 10 帧容量超限怎么产品化？** 是「把所有灯效压到 ≤10 帧」还是「保留原设计、写入前显式告警允许截断」？ | ADR-033 修订 5 实锤固件槽位 = 10 帧，超限帧表被静默截断且自校验不报错（现为残缺版在循环）。**前置**：架构侧已把方案决策标为「需真机复现超限行为后再定」（见 `docs/TASK-BREAKDOWN.md` T05.2），决策前需一次真机确认 | 建议：库内上架灯效一律压到 ≤10 帧；帧画布对超限帧表显式告警并阻止写入。**决策前先安排真机复现** |
| Q3 | **ADR-015 的实现范围**：是否包含 events[] 段与社区仓库？ | 原设计 events 段依赖 ingress，ingress 已由 ADR-025 落地，前置条件已满足；但 events 段工作量显著大于 startup 段 | 建议 v0.4 只做 meta + startup + Schema/validate/导入器，events 段留 v0.5 |
| Q4 | **临时与敏感素材的归属**：`.design-refs` 等设计参考、飞智空间站反编译产物、tools 下一次性脚本，是否随仓库分发？是否进 `.gitignore`？ | 涉及 GPLv3 合规与反编译产物的版权敏感性；也影响仓库体积与新人上手 | 建议：反编译产物一律不入库（只留结论文档），临时素材目录进 `.gitignore`，另开议题确认 |
| Q5 | **测试区（ExpLab）15 项的转正机制**：谁来拍「好用/不好用」？多久清一次待测？判定后是迁正式导航还是下架？ | 判定账本机制已建（ADR-026），但无节奏约定，长期会堆积 | 建议：每版本评审一次，判定「好用」的写转正 ADR 并迁入正式导航；超两版仍「待测」的默认下架 |
| Q6 | **硬件支持范围是否长期严守 Apex 5 单型号？** 若未来要支持八6（协议已变），是开新项目还是本项目开分支？ | ADR-002 明确不追八6 X-Haptics；但八6 用户会有需求 | 建议：严守单型号；八6 另起仓库（协议分叉，共用成本有限） |
| Q7 | **版本号与发布物是否对齐？** `VERSION` 已是 **0.3.2**，但仓库本地 tag 只到 **v0.1.0**；README 让用户去 Releases 下载最新版 | 架构核对发现的版本发布断链。远端是否已有 v0.2/v0.3 Release 尚未核实（需联网确认）；**打 tag 是不可逆操作** | 建议：先联网核实远端 Release 现状，再决定补打 v0.3.2 tag 的时机与负责人；在核实前不要凭空打 tag |
| Q8 | **11 个脚本式自检怎么分类？** 是全部 pytest 化纳 CI，还是按「能否离线跑」分两堆？ | 实测发现它们**并不同质**：`test_led.py` 头部自述「纯函数 + Mock 链路，不碰真机」→ 可安全 pytest 化进 CI；`test_grip_real.py` 头部自述「**真机校准**……走运行中后端的 HTTP API」→ 依赖服务 + 真机，**纳 CI 会恒红** | 建议：**分类处理**（对应 P2-9 已按此改写）——离线可跑者 pytest 化；依赖服务/真机者保留 `python test_x.py` 手动脚本形态并加 `marker` 显式跳过。不要一刀切 pytest 化 |

---

## 附录 A · 已实现能力 → 模块 / ADR 速查

| 能力域 | 后端 | 前端 | 主要 ADR |
|---|---|---|---|
| 协议引擎 / 设备 | `engine.py`、`transport.py`、`protocol.py` | — | ADR-010/011/012 |
| 扳机 / 预设 | `routers/control.py`、`presets.py` | `TriggerLab.tsx`、`PresetLibrary.tsx` | ADR-003 |
| 游戏库 / 适配 | `gameprofiles.py`、`officialimport.py`、`routers/games.py` | `GameLibrary.tsx` | ADR-008/014/017/022/024 |
| Mod / ingress | `modmgr.py`、`dsxingress.py`、`routers/settings.py` | `GameLibrary.tsx`（Mod 卡） | ADR-009/025 |
| 宏 | `macro.py`、`routers/macro.py` | `Macros.tsx` | ADR-021/032 |
| 拓展键 | `extkeys.py`、`extkeymap.py`、`keymonitor.py` | `PadTest.tsx` | ADR-016/019/030/031 |
| 灯光 | `protocol.led_*`、`routers/led.py` | `Lights.tsx` | ADR-018/033/034 |
| 屏幕 | `screenpack.py`、`screenota.py`、`routers/screen.py` | `Screen.tsx` | ADR-018 |
| 体感 | `motionmaster.py`、`softmap.py`、`dsu.py`、`maze.py`、`rawstream.py` | `Motion.tsx` | ADR-027/028 |
| 震动修复 / 设置 | `vibfix.py`、`routers/settings.py` | `Settings.tsx` | — |
| 测试区 | `explab.py`、`routers/explab.py`、`sharecode.py`、`devcfg.py`、`diag.py`、`rgbbridge.py`、`gamesim.py` | `ExpLab.tsx` | ADR-026/027 |
| 壳 / 运维 | `main.py`、`tray.py`、`icon.py`、`routers/system.py`、`wsbus.py` | `App.tsx`、`Offline.tsx` | ADR-004/005/006/013 |

## 附录 B · 已废弃路线（不得写回需求池）

| 路线 | 状态 | 依据 |
|---|---|---|
| DS 虚拟手柄桥接（ASB + usbip + HidHide） | 全量删除，代码零残留 | ADR-020 revB |
| 游戏音频触觉 / 音频分析 | 已砍 | ADR-001 |
| cmd 87 实时音频流（八5 X-Haptics） | 判死 | ADR-002 |
| 独立 172 宏区方案 | 被真机证伪（属 v3.2 设备路径） | ADR-021 |
