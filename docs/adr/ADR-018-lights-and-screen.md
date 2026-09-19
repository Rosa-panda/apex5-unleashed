# ADR-018 RGB 灯光配置 + 屏幕 GIF 自定义动画

日期：2026-09-19（灯光已实现并真机验证；GIF 为二期，见 R4 红线）

## 背景
用户需求：官方空间站支持 ①RGB 灯光自定义 ②上传 GIF 到手柄屏幕做自定义动画。要求评估并实现；GIF 涉及刷写，用户明确要求**功能完善确认后才真机测试**（防变砖）。

## 逆向结论（两个并行逆向代理，spacestation decomp + asar）

### 灯光：写表驻留，非实时流
- PC 把效果展开成「逐帧 RGB 表」（bean）→ cmd 0xA8(start)+0xA9(20B/包) 写入固件 → 固件自己循环播放。锁存，与扳机同类。
- cmd：0xA7 读表（多包 ACK，[3]=总包数 [4]=序号 [6..26]=数据，末包 [3]==[4]+1）；0xA8/0xA9 写；0xF5 测试灯（瞬时点色，会被循环帧表立刻覆盖——不能用作可见探针，实测 NACK 且无视觉效果）。
- 帧封装带 **CRC8 累加和**（`sum(frame[3:3+len])`，len=payload+2）——与 51/82/18 的无 CRC 封装不同族。
- bean 布局（V3，真机实读）：`[0]ver_lo [1]=3 [2]clickFeedback [3]loopStart [4]loopEnd [5]loopTime [6]brightness [7]rgbNum [8]ledMode [9]gripSync [10..19]保留FF` + 帧数据（rgbNum×3B×N帧）。
- **真机参数（Apex5，2026-09-19 实读）：V3、12 灯珠、官方默认=彩虹流光（led_mode=7, loop_end=9, loop_time=4）**。

### 屏幕 GIF：走固件升级通道（高风险路径）
- **方案变更（2026-09-19）**：原定「编排官方 FirmwareConsole.exe」改为**移植 openflydigi 的串口 OTA 实现**（MIT 协议，© Mikalai Kaliaha，本地 `flydigi-apex5-re\openflydigi\`）。理由：① 官方工具是不透明二进制，无法离线自检到字节级；② openflydigi 已在同款设备（有线 Apex5）真机验证（测试卡 + 14 帧动画，PROTOCOL.md §8d）；③ 代码透明，每步可断言。
- 链路：HID cmd 0x1F（chipModule=SCREEN=4）→ 设备**追加** USB CDC 串口 VID `FFAA` PID `5555`（HID 节点不消失）→ 921600 8N1 DTR/RTS → OTA 状态机（opcode 11 读图区基址 → 10 版本 → 3 擦 4096 → 5 写 55B/包 → 12 复位）→ 芯片同步 ~15s 自重启。
- 帧格式（离线已实锤）：25604B/帧 = 4B LVGL v8 头（Apex5 = `04 80 02 0a`）+ 160×80 RGB565 **高字节在前**（LV_COLOR_16_SWAP）。早先记录的 "RBSWAP" 即此。容器 = 帧裸拼接。上限 255 帧（协议帧数 1 字节；本机另测 HIA 说明书 ≤150 不属实，以协议为准）。
- **安全边界三条**（移植保持不变）：① 图区基址从芯片读回（opcode 11），一切擦写 = base+offset，CUSTOM_PIC 永不触及程序区（程序区仅 ScreenUpgradeType.PROGRAM 可达，本模块不实现）；② opcode 12 是协议定义的退出；③ 出厂动画随官方空间站自带（`Configs/Controller/k5/default/default_screen_image_*.bin`），可官方恢复。
- 耗时实测（openflydigi §8d）：约 24.7s/帧（1 帧 ≈ 25s，14 帧 ≈ 5m46s），UI 必须明示预计耗时。
- 陷阱备忘：SDK 的 HID 图片族（cmd 208-211）在 Apex5 上**逐包 ACK 但面板永不亮**（k5 主控不转发给 Freq 屏芯），勿走；cmd 242 测试屏会连 RGB 灯一起染色且关不掉（只能电源开关救），禁用作探针；0xF5 同理不可用。
- 附带发现（**2026-09-19 已实现并真机验证**）：cmd 19/8 状态栏常亮、19/9 息屏显示（动画常亮，实测语义：1=持续播放，0=灭屏、Logo 键临时点亮）。
  读 = cmd 3 整块（sub9 enabled=body[8]&1，sub8 enabled=body[6]&0x80）；写 = cmd 19 `[sub_id, value]`；
  ACK 不证明对应位生效，UI 写后读回复核。端点 /api/screen/{flags,animation,statusbar}，「屏幕」页开关。

## 决定
1. **灯光已实现**（v0.3，本次）：protocol.py 增 CRC 封装/bean 编解码/四类效果展开（solid/breath/gradient/flow）；engine.py `led_read_config/led_write/led_apply_effect`；service `/api/led/{test,config,apply,backup,restore}`；前端「灯光」页（模式/颜色/亮度/帧距/快捷预设）。
2. **写后自校验**：led_write 完成后 0xA7 读回 blob 比对，不符重发一次（实测存在单包 ACK 丢失；0xF5 NACK 与首版写入「成功但不生效」由此发现——实为显示切换延迟+丢包）。
3. **灯表备份强制先于首次写入**：官方默认彩虹 blob 存 `%APPDATA%\Apex5Unleashed\led_backup.bin`，`/api/led/restore` 一键恢复（对官方软件友好：官方也可重设默认）。
4. **GIF 二期红线（用户指令）**：实现顺序 = bin 打包 + 串口 OTA 移植 → 离线自检全绿 → **真机烧写测试必须等用户点头**。
   离线自检（`backend/test_screen_offline.py`，13 项全绿，2026-09-19）：帧格式往返、官方 6 个出厂 bin 共 550 帧全解析、
   GIF→bin 打包、与 openflydigi 原版**逐字节差分**（帧编码/checksum/5 种 opcode 包构造）、Mock 芯片全流程演练
   （含擦写地址 ≥ 读回基址的安全断言）。`/api/screen/flash` 有 confirm=true 红线闸门，UI 两步确认 + 预计耗时明示。
   许可合规：openflydigi 为 MIT，移植部分在文件头署名，GPLv3 兼容。

## 后果
- 灯光全自定义（颜色/亮度/速度/多色渐变流光），写驻留即所见即所得；恢复备份可回官方彩虹。
- GIF 不需要逆向 FREQ 芯片 IAP 协议（编排官方工具即可），风险集中在「切升级模式」一步——设备会重枚举（PID 可能变化），我们的 HID 监控需能重新认领设备（monitor_loop 已有热插拔轮询）。

## 风险
- 灯光效果展开曲线（呼吸 ramp/流光相位）是自拟线性/插值，非官方原版曲线；后续可 0xA7 读官方效果帧表照抄。
- brightness/loop_time 语义已真机标定（2026-09-19）：bean[6] 亮度**真实有效**（255 全亮 → 30 明显变暗，用户目视确认）；
  官方默认 brightness=1 却全亮是官方 UI 标度不同（疑似 1-100%），我们 UI 直接暴露 1-255 原值。
  注意：写入后固件落表有延迟（~0.3s），校验读回必须先等 settle 再读，否则读到旧值误报。
- 校验比对只比重叠前缀：固件帧表槽位固定容量，读回长度可能长于写入（尾部残留旧帧）或短于写入（截断）。
- GIF 烧写：屏幕芯片变砖风险理论上存在（虽然官方工具自带恢复参数）；按 R4 红线执行。
