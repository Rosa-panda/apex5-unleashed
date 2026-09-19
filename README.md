# Apex5 Unleashed

> 开源的飞智八爪鱼5（Apex 5）PC 工具箱 —— 释放官方不给你的那部分能力。

[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-blue)](LICENSE)

## 这是什么

一个让 Apex 5 在 PC 上发挥全部硬件潜力的工具：

- **扳机实验室**：六种自适应扳机模式（Normal / Race / Sniper / Recoil / Lock / Vibration）全参数实时调校，预览模式调参即生效
- **预设库**：内置游戏风格预设 + 自定义预设保存/一键应用（事务式，失败自动回滚）
- **代理权感知**：检测手柄是否被飞智空间站 / Steam / DualSenseX 等接管并提示
- **锁存账本**：软件所见状态 = 手柄真实状态；启动卫生检查自动清理异常残留
- **可观测性**：命令级事件日志（收发 / ACK / 超时 / 外部命令铁证）

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

- **v0.1** ✅ 协议引擎 + 扳机实验室 + 预设库 + 托盘 + Mock 全链路
- **v0.2** DualSense 虚拟手柄桥接（游戏事件级自适应扳机）、DSX UDP 7878 兼容输入、前台进程检测自动切预设
- **v0.3** 社区预设分享、驱动级桥接

## 文档

`docs/TECH-SPEC.md` · `docs/PROTOCOL.md` · `docs/TEST-PLAN.md` · `docs/RISK-REGISTER.md` · `docs/adr/`

## 许可

GPLv3 —— 允许商用，但衍生作品必须开源回馈。
