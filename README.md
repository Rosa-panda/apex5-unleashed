# Apex5 Unleashed

> 开源的飞智八爪鱼5（Apex 5）PC 工具箱 —— 释放官方不给你的那部分能力。

[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-blue)](LICENSE)

## 这是什么

一个让 Apex 5 在 PC 上发挥全部硬件潜力的工具：

- **扳机实验室**：六种自适应扳机模式（Normal / Race / Sniper / Recoil / Lock / Vibration）全参数实时调校，预览模式调参即生效
- **预设库 / 游戏库**：内置预设 + 自定义预设；前台进程自动切换。游戏适配四档：**官方适配**（飞智手工调参震动联动）/ **DS转官**（211 款原生 DualSense 游戏，参数按题材从官方调参自动学习生成，ADR-024）/ **Mod 条目**（官方事件级 Mod，见下）/ 通用震动联动（任意游戏兜底）
- **官方 Mod 管家**：一键下载安装官方 CDN 的游戏 Mod（44 条），DSX UDP ingress 把 Mod 的事件级扳机效果实时转译到手柄（ADR-025）；兼容 DSX 社区 mod 生态
- **游戏震动修复**：自动检测飞智空间站虚拟手柄抢占 XInput 0 号槽（原神等只认 0 号槽的游戏不震的根因），一键临时修复（退出自动还原）或永久修复，全程账本留痕
- **板载宏**：宏写进手柄固件（≤5 条 / 128 步 / 10ms 精度），关软件照样触发；支持录制、循环、整机备份
- **拓展键映射**：六个背键/头键改键写配置区，附测试模式
- **灯光 / 屏幕**：RGB 灯效配置 + 屏幕 GIF 动画自定义
- **代理权感知**：检测手柄是否被飞智空间站 / Steam / DualSenseX 等接管并提示（总线级铁证 + 进程归因）
- **锁存账本**：软件所见状态 = 手柄真实状态；启动卫生检查自动清理异常残留
- **可观测性**：命令级事件日志（收发 / ACK / 超时 / 外部命令铁证 / 孤儿回复计数）

基于对飞智私有 HID 协议的实机逆向（`docs/PROTOCOL.md`），非官方产品，与飞智无关。

## 快速开始

```powershell
# 后端依赖
pip install -r backend/requirements.txt

# 前端构建（已含 dist 可跳过）
cd frontend && npm install && npm run build && cd ..

# 启动（无手柄也能跑，自动 Mock 模式）
python backend/run.py          # GUI + 托盘
python backend/run.py --mock   # 强制 Mock
python backend/run.py --no-gui # 无窗口（开发/CI）
```

## 路线图

- **v0.1** ✅ 协议引擎 + 扳机实验室 + 预设/游戏库 + 灯光 + 屏幕 + 拓展键 + 板载宏 + 托盘 + Mock 全链路
- ~~v0.2 DS 虚拟手柄桥接~~ **已废弃**（ADR-020：PC 上 DualSense 输入实际依赖 Steam Input 翻译层，消费端结构性缺失；外部驱动依赖风险不值，代码全量删除；DS 原生游戏改为无桥的 DS转官参数方案，ADR-024）
- **v0.2** ✅ 官方 Mod 管家 + DSX UDP ingress（ADR-025）+ 游戏震动修复
- **下一步** 统一游戏配置格式（ADR-015）、社区预设分享、XGameMonitor 型 Mod 真机抽测

## 文档

`docs/TECH-SPEC.md` · `docs/PROTOCOL.md` · `docs/TEST-PLAN.md` · `docs/RISK-REGISTER.md` · `docs/adr/` · `docs/REFERENCES.md`

## 参考项目与致谢

站在这些项目和数据源肩膀上（详细清单见 [`docs/REFERENCES.md`](docs/REFERENCES.md)）：

- [ApexSenseBridge（ASB）](https://github.com/ReynArts/ApexSenseBridge)——211 款原生 DualSense 自适应扳机游戏清单（DS转官档案的元数据来源）
- [DualSenseX](https://github.com/Paliverse/DualSenseX)——DSX UDP 协议参考（官方 Mod / 社区 mod 兼容层的协议基础）
- PCGamingWiki——自适应扳机游戏支持清单的原始出处
- 飞智空间站——官方逐游戏调参数据与 Mod 生态（逆向解析，与飞智官方无关联）

## 许可

GPLv3 —— 允许商用，但衍生作品必须开源回馈。
