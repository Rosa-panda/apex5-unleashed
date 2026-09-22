# ADR-033 灯效「扫描·掠过」——原版扫描残留光瑕疵的修复复刻

日期：2026-09-22 · 状态：已实施

## 背景与病灶

用户最喜欢「扫描」（wipe），但观察到：光流到一循环的末尾后，有一盏灯多亮一拍、
灭了之后下一轮才开始（且期望是流完即重新开始，不该有驻留）。

根因在 `protocol.led_frames_wipe` 的帧序拼接，不在固件：

```
fill = [前缀亮帧×n]        # 帧内容：1,2,…,n 班灯亮
return fill + fill[::-1]   # 序列 = 1,2,…,n, n, n-1,…,1  → 循环回 1
```

拼接点把「全亮帧」和「单灯帧」各重复一次：全亮帧多播一拍（光到头滞留）、
循环末尾单灯帧多播一拍（一盏灯赖着不走才开下一轮）。慢速度下（loop_time 大）
肉眼可见的「卡顿+残留光」。

## 裁决

- **原版 wipe 一字不动**（用户明确要求保留对照）。
- 新增独立灯效 `comet`（UI 名「扫描·掠过」）：带拖尾光头从左扫到右，**完全掠出
  右缘后全灭、立即开下一轮**，全程无驻留帧、无重复帧。
- 帧设计：`tail=4` 级线性拖尾，步数 = rgb_num + tail（末尾 tail 帧为全黑离场帧，
  保证光彻底出界；因表内含全黑帧，不做「长亮」观感）。

## 改动面

- backend `protocol.py`：`led_frames_comet()` + `led_identify` 新增 comet 判定
  （连续 run + 起点单调推进 + 存在全黑离场帧——wipe 无全黑帧，天然区分）。
- backend `engine.py`：`led_apply_effect` 派发表加 comet。
- frontend `Lights.tsx`：Mode/STEPS/ledColor/PadPreview 步数/LIB 卡片。
- 测试：test_led.py 加 comet 生成+识别回环。

## 非目标

- 不改 wipe 生成器、不动原版扫描卡片；
- 不动亮度/帧距标定（MS_PER_LT 沿用）；
- 官方灯表识别逻辑对既有灯效的判定顺序不变（comet 判定插在 wipe 之后、rainbow 之前，
  wipe 无全黑帧不会误判，flow 全帧全亮也不满足「存在全黑帧」）。
