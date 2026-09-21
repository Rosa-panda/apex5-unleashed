# -*- coding: utf-8 -*-
# DSU 协议冒烟：假 engine + 模拟 Yuzu 客户端，验证请求/回包字节级正确性。跑完自删不删均可。
import socket, struct, threading, time, zlib
import dsu

class FakeEngine:
    battery = {"level": 4, "charging": False}
    def set_rumble(self, l, r, duration=None, source="ui"):
        print(f"  [rumble] l={l} r={r} src={source}")

eng = FakeEngine()
svc = dsu.DsuServer(eng)
svc.start(26760)
svc.on_motion({"t": time.monotonic(), "accel": (12.0, -30.0, 4088.0),
               "gyro": (100.0, -50.0, 25.0)})

c = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
c.settimeout(2.0)
c.bind(("127.0.0.1", 0))

def dsuc(msg_type, payload=b""):
    body = struct.pack("<I", msg_type) + payload
    pkt = bytearray(b"DSUC" + struct.pack("<HHI", 1001, len(body), 0) +
                    struct.pack("<I", 1234) + body)
    struct.pack_into("<I", pkt, 8, zlib.crc32(bytes(pkt)) & 0xFFFFFFFF)
    return bytes(pkt)

def recv():
    d, _ = c.recvfrom(512)
    assert d[:4] == b"DSUS", d[:4]
    ver, ln, crc, sid = struct.unpack_from("<HHII", d, 4)
    chk = bytearray(d); struct.pack_into("<I", chk, 8, 0)
    assert (zlib.crc32(bytes(chk)) & 0xFFFFFFFF) == crc, "CRC mismatch"
    return struct.unpack_from("<I", d, 16)[0], d

# 1) 版本
c.sendto(dsuc(0x100000), ("127.0.0.1", 26760))
t, d = recv()
assert t == 0x100000 and struct.unpack_from("<H", d, 20)[0] == 1001
print("1) 版本 1001 ✓")

# 2) 控制器信息（请求 1 个槽）
c.sendto(dsuc(0x100001, struct.pack("<i", 1) + bytes([0])), ("127.0.0.1", 26760))
t, d = recv()
slot, state, model, conn = struct.unpack_from("<4B", d, 20)
mac = d[24:30]; bat = d[30]; pad = d[31]
assert (slot, state, model, conn) == (0, 2, 2, 1) and bat == 4 and pad == 0 and len(d) == 32
print(f"2) 信息包 32B ✓ ident={slot},{state},{model},{conn} bat={bat}")

# 3) 数据订阅（slot 注册）
c.sendto(dsuc(0x100002, bytes([1, 0]) + bytes(6)), ("127.0.0.1", 26760))
d1 = None
nums = []
for _ in range(3):
    t, d = recv()
    assert t == 0x100002 and len(d) == 100, (t, len(d))
    nums.append(struct.unpack_from("<I", d, 32)[0])
    if d1 is None: d1 = d
assert nums == sorted(nums) and nums[2] > nums[0], f"包号应递增：{nums}"
pkt_num = nums[0]
conn_b = d1[31]  # ident 20..30（11B）→ connected=31 → pkt_num 32..35
acc = struct.unpack_from("<3f", d1, 76)
gyr = struct.unpack_from("<3f", d1, 88)
assert conn_b == 1
# accel = (-ax, az, ay)/4096 = (-12, 4088, -30)/4096
assert abs(acc[0] - (-12/4096)) < 1e-6 and abs(acc[1] - 4088/4096) < 1e-6 and abs(acc[2] - (-30/4096)) < 1e-6
# gyro pitch/yaw/roll = (g0, g2, g1)*0.05 = (5.0, 1.25, -2.5)
assert abs(gyr[0] - 5.0) < 1e-6 and abs(gyr[1] - 1.25) < 1e-6 and abs(gyr[2] - (-2.5)) < 1e-6
print(f"3) 数据包 100B ✓ 包号{nums} accel={[round(v,4) for v in acc]} gyro={list(gyr)}")

# 4) 反转 pitch
svc.set_invert(pitch=True)
time.sleep(0.15)
for _ in range(10):      # 排空 set_invert 前发出的旧包（tx 是异步流）
    t, d = recv()
gyr2 = struct.unpack_from("<3f", d, 88)
gyr2 = struct.unpack_from("<3f", d, 88)
print(f"   invert 后 gyro={list(gyr2)} invert={svc.invert}")
assert abs(gyr2[0] - (-5.0)) < 1e-6 and abs(gyr2[1] - 1.25) < 1e-6
print(f"4) invert pitch ✓ {[round(v,2) for v in gyr2]}")

# 5) 非官方震动
c.sendto(dsuc(0x110002, bytes([1, 0]) + bytes(6) + bytes([0, 200])), ("127.0.0.1", 26760))
time.sleep(0.2)
assert svc._rumble == [200, 0]
print("5) 震动 motor0=200 ✓（set_rumble 已打印）")

# 6) 马达数
c.sendto(dsuc(0x110001, bytes([1, 0]) + bytes(6)), ("127.0.0.1", 26760))
found = False
for _ in range(80):
    t, d = recv()
    if t == 0x110001 and len(d) == 32:
        assert d[31] == 2   # ident 11 + motor count → 偏移 20+11=31
        found = True
        break
assert found
print("6) 马达数=2 ✓")

st = svc.status()
print(f"status: enabled={st['enabled']} clients={st['stats']['clients']} sent={st['stats']['motion_sent']} err={st['stats']['last_error']}")
assert st["stats"]["last_error"] is None and st["stats"]["clients"] == 1
svc.stop()
c.close()
print("ALL PASS")
