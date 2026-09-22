# ADR-034 灯效自定义：模板+参数（主）与帧画布（辅）

日期：2026-09-22 · 状态：已实施 v1

## 背景

现有灯效 = 写死在 `protocol.led_frames_*` 生成器里的函数，用户只能改颜色/速度，
改不了图案本身（方向、拖尾长度、圆心、倍速等「逻辑」都在代码里）。
用户提出「让用户自己编织灯效」。

## 关键约束（本日实测）

- 固件只会循环连播帧表，**没有任何可编程逻辑**——一切「用户逻辑」都必须由
  工具编译成 ≤10 帧的帧表（槽位容量实测 10 帧，ADR-033 修订 5）。
- loop_time 全表统一一个值、亮度全局一个值、无逐帧时长/插值。

## 裁决

1. **模板+参数（主路径）**：把生成器的写死参数暴露为 UI 旋钮，
   `POST /api/led/apply` 增 `params: dict` 透传到生成器 kwargs：
   - `comet`：`reverse`（方向 左→右 / 右→左）
   - `rain`：`tail`（拖尾长度 1..5）
   - `chase`：`speed_b`（色 B 倍速 2..5）
   - `pulse`：`center`（脉冲圆心灯位）
   - `duosweep`：`blend`（相遇融合开关）
   生成器加对应 kwargs；其余 mode 忽略未知 params（`**kw` 吞掉）。
2. **帧画布（辅路径）**：12 灯 × 10 帧颜色网格，直接直写 `POST /api/led/apply_frames`
   （ADR-033 修订 4 加的诊断端点转正）。工具：全黑帧/复制上帧/整行平移/清空；
   本地保存（localStorage），读回哈希匹配显示名字。
3. **识别跟随参数**：`led_identify` 泛化以覆盖参数化形态——
   - comet 认双向（前缀/后缀两种前缀形态）
   - pulse 认任意圆心（各帧 run 的 (a+b) 恒定 = 圆心指纹，宽度 ≥3 档）
   - rain/chase/duosweep 判据本就与 tail/speed_b/blend 无关，不需改
4. **不做**：规则积木（C 档，用户堆「每帧左移+补色」类规则）——设计空间大、
   易做成半吊子编程语言，待 A/B 用一阵子再评估。

## 非目标

- 不动协议字节、不动 loop/亮度模型；
- 不给 fire/auroraflow/typewriter 等加参数（下架/低频，等需求）；
- 帧画布不做逐帧时长（固件不支持）。

## 改动面

- backend `protocol.py`：comet/pulse/chase/duosweep 生成器加 kwargs；identify 泛化。
- backend `engine.py`：`led_apply_effect(..., params=None)`，派发表改统一 `(cn, cs, **kw)` 签名。
- backend `routers/led.py`：`LedApplyReq.params: dict = {}`。
- frontend `Lights.tsx`：参数旋钮区（按模式显隐）+ 预览镜像参数。
- frontend `api/lights.ts`：`ledApply` 加 params；`ledApplyFrames`。
- 测试：test_led.py 补参数化生成+识别回环。

## 附带修复

- `TriggerLab.tsx`：默认参数 effect 依赖 `[mode]` → `[fields]`（字段表异步晚到时
  params 恒空、显示全 0 的 bug，2026-09-22 用户报）。
