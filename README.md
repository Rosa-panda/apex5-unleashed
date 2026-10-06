# Apex5 Unleashed

> 开源的飞智八爪鱼5（Apex 5）PC 工具箱 —— 扳机调校、游戏适配、板载宏、灯光屏幕、体感桥接，一个工具管全。

[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-blue)](LICENSE)

## 这是什么

基于对飞智私有 HID 协议的实机逆向（`docs/PROTOCOL.md`），为 Apex 5 提供一套官方软件之外的 PC 端管理与调校工具。非官方产品，与飞智无关。

- **扳机实验室**：六种自适应扳机模式（Normal / Race / Sniper / Recoil / Lock / Vibration）全参数实时调校，预览模式调参即生效
- **预设库 / 游戏库**：内置 ~280 款游戏适配档案，前台进程自动切换；支持自定义预设与自定义 exe 定位。适配分五档：**官方适配**（飞智手工调参震动联动）/ **DS转官**（原生 DualSense 游戏，参数按题材从官方调参自动学习生成，ADR-024）/ **DS转官·通用** / **题材适配** / **Mod 条目**（官方事件级 Mod，见下）。默认不套预设，绑不绑定由你决定
- **官方 Mod 管家**：一键下载安装官方 CDN 的游戏 Mod，DSX UDP ingress 把 Mod 的事件级扳机效果实时转译到手柄（ADR-025）；顺带兼容 DSX 社区 mod 生态。Mod 本体不随软件分发，只做下载引导 + 事件翻译
- **体感中心**：体感总闸（状态持久化，重启自动恢复）+ 体感四件套——陀螺瞄准（软件层映射）、固件陀螺映射、DSU/Cemuhook 桥（UDP 模拟，Yuzu / Cemu / Dolphin / PCSX2 可直接识别，真机 97Hz 实测）、迷宫试玩场（弹珠物理，练手感用）
- **板载宏**：宏写进手柄固件（≤5 条 / 全部 ≤128 步 / 10ms 精度），关软件照样触发；支持录制、单次 / 按住循环 / 点击循环、循环间隔、复制、导入导出 JSON、整机备份恢复。触发键为六个拓展键（固件直出）
- **拓展键**：六个背键/头键在手柄图上**即按即亮**（实时回显，按 M 键图上 M 键亮）；可选映射到手柄按键或键盘按键，默认透传；被宏占用的键会锁定并标注
- **灯光工坊**：RGB 灯效库 + 速度 / 亮度调节（真机标定）、进页自动还原当前灯效（含非库内「外来灯效」逐帧回放）、一键关灯、灯表备份恢复
- **屏幕**：自定义 GIF 动画写入手柄屏幕（自动抽帧保原速，串口 OTA 烧写，已真机验证）
- **测试区**：一组进阶实验功能——按键曲线编辑、扳机行程、连发（Turbo）、设备设置、四槽档案管理、摇杆→键鼠映射、RGB 桥接、分享码导入导出、摇杆诊断散点、恢复出厂等。写操作均有确认闸门与备份，实验项请自行评估
- **游戏震动修复**：自动检测飞智空间站虚拟手柄抢占 XInput 0 号槽（原神等只认 0 号槽的游戏不震的根因），一键临时修复（退出自动还原）或永久修复，全程账本留痕
- **状态与可观测性**：电量显示（含充电态）、代理权感知（检测飞智空间站 / Steam / DualSenseX 等接管，总线级证据 + 进程归因）、锁存账本（软件所见 = 手柄真实状态）、命令级事件日志

**能力边界（诚实声明）**：DualSense 原生游戏的「事件级」自适应扳机效果，是游戏运行时发给 DualSense 硬件的报告流——手柄本身不 DualSense 时这些数据根本不存在，无法凭空还原。我们能做的是转译其**体验**（逐游戏震动参数包），而非配置本身；事件级效果请走官方 Mod 管家路线。

## 快速开始

### 普通用户（推荐）

到 [Releases](https://github.com/Rosa-panda/apex5-unleashed/releases) 下载最新 `Apex5Unleashed-v*-win64.zip`，解压后双击 `Apex5Unleashed.exe` 即可——无需安装 Python 或 Node。运行日志在 `%APPDATA%\Apex5Unleashed\apex5.log`。

### 开发者（源码运行）

```powershell
# 后端依赖
pip install -r backend/requirements.txt

# 前端构建（已含 dist 可跳过）
cd frontend && npm install && npm run build && cd ..

# 启动（无手柄也能跑，自动 Mock 模式）
python backend/run.py          # GUI + 托盘
python backend/run.py --mock   # 强制 Mock
python backend/run.py --no-gui # 无窗口（开发/CI）

# 开发者：跑测试（详见 docs/DEV-STATUS.md §6）
python -m pytest backend -q          # pytest 式单测
python tools/run_script_tests.py     # 脚本式单测（CI 名单）
python tools/run_smoke.py            # Mock 全链路冒烟（自动起/收服务）
python tools/check_version.py        # 版本一致性（发版前自校验）
```

> ⚠ **安全提示**：持续高负载马达（长时间高强度震动 / 满亮度灯效）会加速电机老化并明显缩短续航，
> 请按需使用、不用时通过托盘退出（`Apex5Unleashed` 会在退出时做卫生清理）。

## 文档

| 文档 | 内容 |
|---|---|
| [`docs/DEV-STATUS.md`](docs/DEV-STATUS.md) | **当前状态锚点**（版本 / 安全点回退 / 已知坑 / 本地跑法 / 真机验收记录表）——新人从这里开始 |
| [`docs/PRD.md`](docs/PRD.md) | 需求基线（做什么 / 为什么）：需求池 P0-P2、边界条款、待确认问题、能力域速查 |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 架构定稿（代码怎么组织）：五层分层、模块结构、数据流、文档↔实现偏差表 |
| [`docs/TECH-SPEC.md`](docs/TECH-SPEC.md) | 技术规格：线程约定、参数标定、接口清单 |
| [`docs/PROTOCOL.md`](docs/PROTOCOL.md) | 协议规范（字节怎么排）：HID 帧 / 命令集 / 电量 / 已知坑 |
| [`docs/RELEASE.md`](docs/RELEASE.md) | 发版 SOP：改 `VERSION` → push → CI 自动打包发版；手动补 tag 步骤 |
| [`docs/TEST-PLAN.md`](docs/TEST-PLAN.md) | 测试计划：v0.1 / v0.2 / v0.3 验收条目 + CI 策略与排除项 |
| [`docs/RISK-REGISTER.md`](docs/RISK-REGISTER.md) | 风险登记册（R1–R13，每版本评审） |
| [`docs/TASK-BREAKDOWN.md`](docs/TASK-BREAKDOWN.md) | 任务分解（T01–T05）与待拍板事项 |
| [`docs/RESEARCH-HIDDEN-FEATURES.md`](docs/RESEARCH-HIDDEN-FEATURES.md) | 隐藏功能挖掘实录（16 项功能的逆向与实测结论） |
| [`docs/REFERENCES.md`](docs/REFERENCES.md) | 参考项目与致谢清单 |
| [`docs/adr/`](docs/adr/) | 架构决策记录（ADR-001~034，索引起点 `docs/adr/ADR-INDEX.md`） |

## 路线图

- **v0.1** ✅ 协议引擎 + 扳机实验室 + 预设/游戏库 + 灯光 + 屏幕 + 拓展键 + 板载宏 + 托盘 + Mock 全链路
- **v0.2** ✅ 官方 Mod 管家 + DSX UDP ingress（ADR-025）+ 游戏震动修复 + 游戏库五档适配
- **v0.3** ✅ 体感线（陀螺瞄准 / DSU 桥 / 体感总闸，ADR-027/028）+ 灯光工坊 + 拓展键映射与宏完善（ADR-030/031/032）+ Windows 打包发布
- ~~DS 虚拟手柄桥接~~ **已废弃**（ADR-020：PC 上 DualSense 输入依赖 Steam Input 翻译层 + 虚拟驱动隔离伤及无辜，代码全量删除；改走无桥的 DS转官参数方案，ADR-024）
- **下一步** 屏幕动画打磨（恢复出厂入口）、XGameMonitor 型 Mod 真机抽测、统一游戏配置格式（ADR-015）、分享码社区生态

## 参考项目与致谢

站在这些项目和数据源肩膀上（详细清单见 [`docs/REFERENCES.md`](docs/REFERENCES.md)）：

- [ApexSenseBridge（ASB）](https://github.com/ReynArts/ApexSenseBridge)——原生 DualSense 自适应扳机游戏清单（DS转官档案的元数据来源）
- [DualSenseX](https://github.com/Paliverse/DualSenseX)——DSX UDP 协议参考（官方 Mod / 社区 mod 兼容层的协议基础）
- [openflydigi](https://github.com/mkaliaha/openflydigi)——档案 blob 布局与屏幕 OTA 方案的参考实现（MIT）
- PCGamingWiki——自适应扳机游戏支持清单的原始出处
- 飞智空间站——官方逐游戏调参数据与 Mod 生态（逆向解析，与飞智官方无关联）

## 许可

GPLv3 —— 允许商用，但衍生作品必须开源回馈。
