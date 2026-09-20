# Apex5 Unleashed

> 开源的飞智八爪鱼5（Apex 5）PC 工具箱 —— 释放官方不给你的那部分能力。

[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-blue)](LICENSE)

## 这是什么

一个让 Apex 5 在 PC 上发挥全部硬件潜力的工具：

- **扳机实验室**：六种自适应扳机模式（Normal / Race / Sniper / Recoil / Lock / Vibration）全参数实时调校，预览模式调参即生效
- **预设库 / 游戏库**：内置预设 + 自定义预设；前台进程自动切换。游戏适配三档：**官方适配**（飞智手工调参震动联动）/ **DS转官**（211 款原生 DualSense 游戏，参数按题材从官方调参自动学习生成，ADR-024）/ 通用震动联动（任意游戏兜底）
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
- **下一步** 统一游戏配置格式（ADR-015）、社区预设分享、DSX UDP ingress（待定）

## 文档

`docs/TECH-SPEC.md` · `docs/PROTOCOL.md` · `docs/TEST-PLAN.md` · `docs/RISK-REGISTER.md` · `docs/adr/`

## 许可

GPLv3 —— 允许商用，但衍生作品必须开源回馈。
