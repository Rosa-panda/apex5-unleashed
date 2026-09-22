# ADR-018 灯光协议单测（纯函数 + Mock 链路，不碰真机）
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))

import protocol as p

# 1. CRC 封装：对照官方示例 03 5A A5 F5 05 R G B crc（crc=sum([F5,05,R,G,B])）
f = p.led_test_frame(0xFF, 0x00, 0x00)
assert f[:5] == bytes([0x03, 0x5A, 0xA5, 0xF5, 0x05]), f[:5].hex()
assert f[5:8] == b"\xff\x00\x00"
assert f[8] == p.crc8_sum(f[3:8]), f[8]
assert len(f) == p.PACKET_LEN
print("1. led_test_frame OK:", f[:9].hex(" "))

# 2. 读/写帧
rf = p.led_read_frame(0)
assert rf[3] == 0xA7 and rf[4] == 4 and rf[5:7] == b"\x00\x14"
assert rf[7] == p.crc8_sum(rf[3:7])
sf = p.led_write_start_frame(0, 25)
assert sf[3] == 0xA8 and sf[5:8] == bytes([0, 0, 25]) and sf[8] == 20
pf = p.led_write_pack_frame(3, bytes(range(20)))
assert pf[3] == 0xA9 and pf[5] == 3 and len(pf[6:26]) == 20
print("2. read/start/pack frames OK")

# 3. bean 解析 V2/V3
v2 = bytes([0, 2, 1, 0, 15, 10, 128, 10, 1]) + b"\xff" * 11 + b"\x00" * 480
b2 = p.parse_led_bean(v2)
assert b2 and b2["version"] == 2 and b2["rgb_num"] == 10 and b2["brightness"] == 128, b2
v3 = bytes([0, 3, 0, 0, 15, 10, 200, 16, 1, 1]) + b"\xff" * 10 + b"\x00" * 480
b3 = p.parse_led_bean(v3)
assert b3 and b3["version"] == 3 and b3["rgb_num"] == 16 and b3["grip_sync"] == 1, b3
assert p.parse_led_bean(b"\x00" * 20) is None
print("3. parse_led_bean OK")

# 4. 帧展开
solid = p.led_frames_solid((255, 0, 0), 10)
assert len(solid) == 30 and solid[:3] == b"\xff\x00\x00"
breath = p.led_frames_breath((0, 255, 0), 10, steps=16)
n_f = len(breath) // 30
assert len(breath) % 30 == 0 and n_f == 16, len(breath)
assert breath[1] == 0 and max(breath[i * 30 + 1] for i in range(n_f)) == 255
assert breath[(n_f - 1) * 30 + 1] < 40      # 末帧接近熄灭（ramp 最低非零档）
grad = p.led_frames_gradient([(255, 0, 0), (0, 0, 255)], 10)
assert len(grad) == 16 * 30
flow = p.led_frames_flow([(255, 0, 0), (0, 0, 255)], 10)
assert len(flow) == 16 * 30

# 4b. comet（ADR-033 修订）：逐珠点亮 1..n 共 n 帧，铺满即回表首——无排空半程、无重复帧
comet = p.led_frames_comet([(0, 170, 255)], 12)
n_c, cf = len(comet) // 36, 12 * 3
assert n_c == 12, n_c
frames_c = [comet[i * cf:(i + 1) * cf] for i in range(n_c)]
lit_c = [sum(1 for j in range(12) if max(f[j * 3:j * 3 + 3]) > 0) for f in frames_c]
assert lit_c == list(range(1, 13)), lit_c                # 严格 1..n 单调递增
assert frames_c[0] != frames_c[-1]                       # 首尾帧不同（无拼接重复）
assert all(f[:3] == b"\x00\xaa\xff" for f in frames_c)   # 配色原样（无缩放）
wipe = p.led_frames_wipe([(0, 170, 255)], 12)
wf = [wipe[i * cf:(i + 1) * cf] for i in range(len(wipe) // cf)]
lit_w = [sum(1 for j in range(12) if max(f[j * 3:j * 3 + 3]) > 0) for f in wf]
assert lit_w[11] == 12 and lit_w[12] == 12               # 原版病灶对照：全亮帧表内重复
assert lit_w[23] == 1 and lit_w[0] == 1                  # 单灯帧跨循环边界重复（残留光根源）

# 4c. comet 识别回环 + 与 wipe/flow 不互混
blob_c = p.led_bean_header(b3, p.led_frames_comet([(0, 170, 255)], 16))
d = p.led_identify(blob_c)
assert d["mode"] == "comet" and d["known"] and d["colors"] == [[0, 170, 255]], d
assert p.led_identify(p.led_bean_header(b2, p.led_frames_wipe([(0, 170, 255)], 10)))["mode"] == "wipe"

# 4d. duosweep（ADR-033 修订 2）：两色相向铺满，会合即重开
duo = p.led_frames_duosweep([(0, 170, 255), (255, 0, 140)], 12)
n_d = len(duo) // 36
assert n_d == 6, n_d                                     # ceil(12/2)
frames_d = [duo[i * 36:(i + 1) * 36] for i in range(n_d)]
assert frames_d[0][0:3] == b"\x00\xaa\xff"               # 左端 A
assert frames_d[0][-3:] == b"\xff\x00\x8c"               # 右端 B
assert frames_d[0][3:33] == b"\x00" * 30                 # 首帧中缝全黑
lit_d = [sum(1 for j in range(12) if max(f[j * 3:j * 3 + 3]) > 0) for f in frames_d]
assert lit_d == [2, 4, 6, 8, 10, 12], lit_d              # 相向各 +1，末帧铺满
assert frames_d[-1][:18] == b"\x00\xaa\xff" * 6          # 末帧左半 A
assert frames_d[-1][18:] == b"\xff\x00\x8c" * 6          # 末帧右半 B
d_duo = p.led_identify(p.led_bean_header(b3, p.led_frames_duosweep([(0, 170, 255), (255, 0, 140)], 16)))
assert d_duo["mode"] == "duosweep" and d_duo["known"] and d_duo["colors"] == [[0, 170, 255], [255, 0, 140]], d_duo
print("4b/4c/4d. comet+duosweep expansion + identify OK")

# 5. blob 组装：20B 头（保持版本字节/保留区）+ 帧数据
blob = p.led_bean_header(b2, solid)
assert len(blob) == 20 + len(solid)
assert blob[0] == 0 and blob[1] == 2 and blob[7] == 10 and blob[8] == 1
assert blob[9:20] == b"\xff" * 11
print("5. bean blob OK")

# 6. Mock 引擎链路
import engine as m
import transport
eng = m.Engine(force_mock=True)
eng.attach(transport.MockPad())
time.sleep(0.2)
eng.led_test(0, 255, 0, source="t")
bean = eng.led_read_config(source="t")     # Mock ACK 首包即"完成"，blob 全零 → None
assert bean is None, bean                  # 真机才有真 bean
print("6. mock engine chain OK (bean=None expected)")

eng.stop()
print("ALL LED PROTOCOL TESTS PASS")
