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

# 4d. duosweep（ADR-033 修订 4）：两色相向铺满→相遇融合→表尾喘息两拍→重开
duo = p.led_frames_duosweep([(0, 170, 255), (255, 0, 140)], 12)
n_d = len(duo) // 36
assert n_d == 8, n_d                                     # ceil(12/2) + 2 喘息拍
frames_d = [duo[i * 36:(i + 1) * 36] for i in range(n_d)]
assert frames_d[0][0:3] == b"\x00\xaa\xff"               # 左端 A
assert frames_d[0][-3:] == b"\xff\x00\x8c"               # 右端 B
assert frames_d[0][3:33] == b"\x00" * 30                 # 首帧中缝全黑
lit_d = [sum(1 for j in range(12) if max(f[j * 3:j * 3 + 3]) > 0) for f in frames_d]
assert lit_d == [2, 4, 6, 8, 10, 12, 0, 0], lit_d        # 相向各 +1，末两拍全黑
meet = frames_d[5]                                       # 相遇拍：两前端融合
assert meet[:15] == b"\x00\xaa\xff" * 5                  # 左段 A
assert meet[15:21] == bytes((127, 85, 197)) * 2          # 两前端融合色
assert meet[21:] == b"\xff\x00\x8c" * 5                  # 右段 B
assert frames_d[6] == b"\x00" * 36 and frames_d[7] == b"\x00" * 36   # 喘息拍
d_duo = p.led_identify(p.led_bean_header(b3, p.led_frames_duosweep([(0, 170, 255), (255, 0, 140)], 16)))
assert d_duo["mode"] == "duosweep" and d_duo["known"] and d_duo["colors"] == [[0, 170, 255], [255, 0, 140]], d_duo
print("4b/4c/4d. comet+duosweep expansion + identify OK")

# 4e. 修订 3 批量灯效：生成 + 识别回环
for mode, colors_in, n_leds in [
    ("rain", [(0, 170, 255)], 12),
    ("chase", [(0, 170, 255), (255, 0, 140)], 12),
    ("pulse", [(255, 40, 90)], 12),
    ("fire", [(255, 120, 30)], 12),
    ("typewriter", [(0, 255, 140)], 12),
]:
    gen = getattr(p, f"led_frames_{mode}")
    tab = gen([tuple(c) for c in colors_in], n_leds)
    assert len(tab) % (n_leds * 3) == 0
    tab16 = gen([tuple(c) for c in colors_in], 16)
    b3x = dict(b3, loop_end=len(tab16) // (16 * 3) - 1)   # 与真实写入路径一致：loop 覆盖全表
    dx = p.led_identify(p.led_bean_header(b3x, tab16))
    assert dx["mode"] == mode and dx["known"], (mode, dx)
    assert all(abs(a - b) <= 2 for a, b in zip(dx["colors"][0], colors_in[0])), (mode, dx["colors"])
af = p.led_frames_auroraflow([(0, 255, 140), (0, 120, 255), (160, 0, 255)], 12)
assert len(af) == 24 * 36
print("4e. batch effects (rain/chase/pulse/fire/typewriter/auroraflow) OK")

# 4f. hueflash（修订 5，用户钦定）：恰 2 帧奇偶交替 + 识别回环
hf = p.led_frames_hueflash(16)
assert len(hf) == 2 * 48, len(hf)
d_hf = p.led_identify(p.led_bean_header(dict(b3, loop_end=1), hf))
assert d_hf["mode"] == "hueflash" and d_hf["known"], d_hf
print("4f. hueflash expansion + identify OK")

# 4g. ADR-034 参数化模板：生成器 kwargs 生效 + 参数化形态仍可识别
# comet 反向：从右往左逐珠点亮（后缀形态）
comet_r = p.led_frames_comet([(0, 170, 255)], 12, reverse=True)
fr_r = [comet_r[i * 36:(i + 1) * 36] for i in range(len(comet_r) // 36)]
lit_r = [sum(1 for j in range(12) if max(f[j * 3:j * 3 + 3]) > 0) for f in fr_r]
assert lit_r == list(range(1, 13)), lit_r
assert max(fr_r[0][33:36]) > 0 and max(fr_r[0][:33]) == 0    # 首帧只亮右端（灯 11）
d_cr = p.led_identify(p.led_bean_header(b3, p.led_frames_comet([(0, 170, 255)], 16, reverse=True)))
assert d_cr["mode"] == "comet" and d_cr["known"], d_cr
# pulse 指定圆心=3（非正中）
pulse_c = p.led_frames_pulse([(255, 40, 90)], 12, center=3)
pc0 = pulse_c[:36]
assert max(pc0[6:12]) > 0 and max(pc0[:6]) == 0 and max(pc0[12:]) == 0   # 首帧 r=1 亮灯 2,3（圆心 3）
d_pc = p.led_identify(p.led_bean_header(b3, p.led_frames_pulse([(255, 40, 90)], 16, center=4)))
assert d_pc["mode"] == "pulse" and d_pc["known"], d_pc
# rain 拖尾长度参数不破坏识别
for tail in (1, 5):
    d_rt = p.led_identify(p.led_bean_header(b3, p.led_frames_rain([(0, 170, 255)], 16, tail=tail)))
    assert d_rt["mode"] == "rain" and d_rt["known"], (tail, d_rt)
# chase 倍速参数不破坏识别
d_cb = p.led_identify(p.led_bean_header(b3, p.led_frames_chase([(0, 170, 255), (255, 0, 140)], 16, speed_b=5)))
assert d_cb["mode"] == "chase" and d_cb["known"], d_cb
# duosweep 关闭融合：相遇拍无混色
duo_nb = p.led_frames_duosweep([(0, 170, 255), (255, 0, 140)], 12, blend=False)
fnb = len(duo_nb) // 36
frames_nb = [duo_nb[i * 36:(i + 1) * 36] for i in range(fnb)]
meet_nb = frames_nb[fnb - 3]                                 # 表尾 2 全黑喘息前的相遇拍
assert not any(meet_nb[i * 3:i * 3 + 3] == bytes((127, 85, 197)) for i in range(12)), "blend off 仍有融合色"
d_nb = p.led_identify(p.led_bean_header(b3, p.led_frames_duosweep([(0, 170, 255), (255, 0, 140)], 16, blend=False)))
assert d_nb["mode"] == "duosweep" and d_nb["known"], d_nb
print("4g. parameterized templates (comet reverse / pulse center / rain tail / chase speed / duosweep blend) OK")

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
