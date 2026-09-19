# ADR-020 DS 桥接「指挥官」模式（任务 #2/#7 软件侧）

日期：2026-09-19（讨论定案：用户拍板"直接上"，模式 1 起步）

## 背景

企划书 v0.2 的 DS 桥接路线（虚拟 DualSense → 原生自适应扳机）经联网调研确认由
[ReynArts/ApexSenseBridge](https://github.com/ReynArts/ApexSenseBridge)（GPL-3.0-or-later，
与我们同许可证）实现为 Windows 唯一成品。驱动链 usbip-win2 + HidHide 为内核级，
**躲不掉**；"开箱即用"的现实定义 = 驱动安装被自动化到无感（ASB 官方 Setup 已做到）。

用户约束：本工具是开源项目，**不能为不玩 PS 移植游戏的用户增加重量**——桥接必须是
选装模块，不用的人和今天一模一样轻。

## 方案选型（三选一）

- **模式 1「指挥官」（采纳）**：不打包任何驱动/二进制。检测 ASB 安装状态 → 引导下载
  官方安装包 → 检测桥接会话并做**总线仲裁** → 提供救砖入口。ASB 替全生态趟驱动雷，
  我们白嫖成果并回馈测试数据。
- 模式 2「吞掉整条链」：自持 VIIPER + DS 补丁自建安装器。否决：接管内核驱动兼容
  （usbip 0.9.7.8 蓝屏级别的雷）不是开源工具箱该背的锅，工作量数倍。
- 模式 3「折中」：模式 1 落地攒够驱动兼容数据后，v0.3 再评估是否静默分发。留待将来。

## 决定

### 1. `app/asb.py` 指挥官模块
- 安装检测：HKLM\Software\ApexSenseBridge 注册表 + `%ProgramFiles%\ApexSenseBridge`
  目录兜底；HidHide / usbip_vhci 以服务注册表键探测。
- 进程检测：tasklist（CREATE_NO_WINDOW，ADR-019 工程坑）。
- 操作面：拉起托盘、打开官方下载页（webbrowser）、救砖（engine exe
  `restore-controller-visibility`）。
- 不做：下载/校验安装包（v0.2 只跳转官方 releases，避免维护镜像与哈希）。

### 2. engine 桥接仲裁（核心冲突解）
- PROXY_NAMES 加 ASB 两进程 → 进程扫描可归因。
- 新增 proxy holder 第三态 `"bridge"`：ASB 进程在场（`_bg_process_hint` 归因到它）时，
  总线外部命令 → holder=bridge，**不发代理警告、不计时夺回、不 reassert**（否则与
  FORCEADAPT 互抢扳机，桥接直接废）。
- 桥接释放：ASB 进程消失且总线外部命令静默超时 → 自动回 self 并重放账本
  （复用 scan_proxy_processes 的 2s 任务列表输出，不加线程）。

### 3. 游戏档案 `ds_bridge` + `prompts` 字段（ADR-014/017 档案体系顺路扩展）
- `ds_bridge: true` 的游戏在**桥接会话中**（engine.proxy.holder=="bridge"）：
  apply_game / maybe_autoswitch 跳过 vib 绑定与预设下发（扳机让位给 ASB），
  非桥接期行为不变（该游戏没装/没开 ASB 时照常震动联动）。
- `prompts: "ps" | "xbox" | "auto"`：纯提示字段，游戏库详情里告知该游戏 DS 模式下
  按键图标样式及游戏内设置位置（缓解"按键显示乱"）。

### 4. service `/api/bridge/*`：status / launch / open-download / restore-visibility；
   `/api/games/{gid}/dsbridge` 开关（内置档案自动复制为用户副本，同 link 语义）。

### 5. 前端：新增「DS 桥接」页（安装引导 / 会话状态 / 冲突说明 / 反作弊免责）；
   头部横幅 bridge 态显示蓝色"DS 桥接中"而非黄色被代理警告；游戏库详情加开关。

## 后果

- 不装 ASB 的用户：零新增重量（一个检测模块 + 一个页面）。
- B1-B5 实测时序：本 ADR 落地 → 用户装 ASB（官方 Setup，管理员+可能重启）→
  按 TEST-PLAN B1-B5 走，重点实测：vendor 0xEF 拓展键流在 HidHide 隐藏后是否幸存、
  pythonw HidHide 白名单、仲裁是否真的不打架。
- 反作弊红线：虚拟 HID 对内核级反作弊网游有理论风险，UI 明示"仅建议单机/合作 PVE"。

## 风险

- ASB 注册表值名未知（文档只说写 HKLM\Software\ApexSenseBridge）→ 代码遍历全部值
  找含 ApexSenseBridge.exe 的路径，目录兜底，B1 实测修正。
- holder=bridge 期间用户点紧急复位：允许（显式用户意图），但 UI 提示先退游戏。
- ASB 烂尾：GPL 同许可证，fork 权完整（VIIPER/DS 补丁均 MIT），最坏自持。
