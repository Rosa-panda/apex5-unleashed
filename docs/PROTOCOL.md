# PROTOCOL · 飞智八爪鱼5 协议规范（规范级，实现以此为准）

> 来源：openflydigi(MIT) + 本项目实机验证（2026-09-17，详见 ../../ANALYSIS.md）+ 官方空间站 SDK 反编译交叉确认。

## 传输

- USB 有线与 2.4G 接收器同 VID:PID `37d7:2501`；vendor 接口 = usage page `0xFFA0`（Windows 路径含 MI_02）
- 出：32B report id 0x03：`03 5A A5 <cmd> <len> <payload…> [checksum?]`
- 入：report id 0x04；ACK 剥 report id 后 `[2]=cmd, [3]=01`（K6 家族成功位在 [5]）
- len = payload 长度（官方 81/82/18 不写校验和也 ACK；需校验时 8-bit 累加和，cmd 87 例外从 [1] 起算）
- ACK 广播给所有读者（多进程抢接口会串包 → 代理权检测的物理基础）
- **所有效果锁存固件**，不发清除不会消失

## 命令（v0.1 使用集）

| cmd | 名 | 载荷（payload 从帧 [5] 起） | 备注 |
|---|---|---|---|
| 0x01 | info | 空 | 回含 device id 0x80(=Apex5) |
| 0x12(18) | rumble | `[L, R]`（帧[5]=L [6]=R） | 流式零等待；锁存需归零 |
| 0x51(81) | SetForceTrigger | `[apply(1/0), side(1L/2R), mode, *params]` | apply=0 为 preview 不落锁存（官方 onlyPreview） |
| 0x52(82) | SyncWithGrip | `[side, bindType=2, filter, scale, stroke, press, strength, freq]` | rumble→扳机路由；解绑 = mode 0 重发 |

81 的 mode 与 params（官方 SDK 反编译确认，钳位照抄）：
- 0 Normal `[side,0]` 清除
- 1 Race `[side,1,stroke,resistance≥1,match]` 恒阻力
- 2 Sniper `[side,2,stroke,press≥1,strength≥1,freq≥1,match]` 机枪振动
- 3 Recoil `[side,3,stroke,recoilStroke,strength≥1,0,match]` 突破阻力（官方固定第6字节0）
- 4 Lock `[side,4,stroke,strength,match]`
- 5 Vibration `[side,5,stroke,press,strength,freq,match]`（官方文档评"残废没人用"，保留兼容）

## 官方对照（逆向佐证，非实现要求）

- 官方 NewXInput 路径：cmd81 帧 len=10、apply 在 [5]；cmd82 len=11 —— 与本规范一致
- 官方另有 XInput(cmd 48)/DInput(cmd 160) 旧路径，不实现
- K6 家族 83-87（八6 X-Haptics）：八5 硬件 ACK-but-ignore，**判死**（ADR-002）
- cmd 17 `[1,1]` 开体感流（~300Hz，0xEF marker），v0.1 不用，v0.3 分发

## 已知坑（勿重踩）

1. 测试前必须 panic 基线（效果锁存污染实验）
2. ACK 成功位偏移：非 K6 命令看 [3]，K6 看 [5]
3. side=3(Both) 会被 ACK 但不执行（官方枚举存在但固件不理）——双侧=分别发 L 和 R

## 电量（cmd1 心跳回复，2026-09-19 真机实证）

- 帧：`5a a5 01 01 00 80 02 | MAC×4 | 电量 | 7组BCD固件版本...`（report id 剥离后）
- body[5]=0x80 设备类型，body[6]=连接方式（0x02=2.4G dongle），body[7..10]=MAC（本机全零），**body[11]=电量字节**
- **电量字节：低半字节 = 电量 0..5（5=满），高半字节 1 = 充电中**。粒度 20%，协议里不存在更细数值（openflydigi 全命令族核查结论）
- 引擎实现：refresh_battery() 发心跳（attach 首发 + monitor_loop 30s 轮询），_classify 抓取（0x80 守门），变化才发 battery 事件；快照 device.battery
- Mock：mock_ack_frame 对 cmd1 伪造 body[11]=0x04，离线 UI 可显