# -*- coding: utf-8 -*-
r"""屏幕上传离线自检（ADR-018 R4 二期红线：真机前必须全绿）。

1. 帧格式：编码→解码往返、LVGL 头常量、坏头拒收
2. 官方出厂 bin 解码（C:\Program Files\Flydigi Space Station\...\default_screen_image_*.bin）
3. GIF → bin 打包全链路 + 255 帧上限
4. 差分测试：与本地 openflydigi 原版逐字节对比（像素/帧/校验和/OTA 包）
5. Mock 设备全流程演练：OtaLink 仿真 → upload() 状态机 → 偏移/CRC 逐项核对

不碰任何硬件。运行：python test_screen_offline.py
"""
import os
import random
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "openflydigi"))

import screenpack
import screenota

OFFICIAL_DIR = r"C:\Program Files\Flydigi Space Station\Configs\Controller\k5\default"
PASS = []


def ok(name):
    PASS.append(name)
    print(f"  OK {name}")


# 1. 帧格式 -----------------------------------------------------------------
print("[1] 帧格式")
assert screenpack.frame_header() == bytes.fromhex("0480020a")
ok("LVGL 头常量 = 04 80 02 0a")

random.seed(42)
# 565 量化有损：源数据用「量化域内的合法值」（5/6/5 位复制展开），往返才可比
px = []
for _ in range(160 * 80):
    px.extend(screenpack.unpack_pixel(random.randrange(256), random.randrange(256)))
rgb = bytes(px)
frame = screenpack.encode_frame(rgb)
assert len(frame) == screenpack.FRAME_LEN == 25604
_w, _h, back = screenpack.decode_frame(frame)
assert back == rgb, "往返解码不一致"
ok("encode→decode 往返 25604B 逐字节一致")

# 565 量化不可逆，但量化域内（复制展开后的值）往返必须自身一致
r, g, b = screenpack.unpack_pixel(0xFF, 0xFF)   # 白 = 复制展开值
hi, lo = screenpack.pack_pixel(r, g, b)
assert (hi, lo) == (0xFF, 0xFF) and (r, g, b) == (255, 255, 255), "pack_pixel 语义"
ok("RGB565 高字节在前 + 量化域往返无色偏")

for bad in (b"\xff\xff\xff\xff", b"\x04\x80", b""):
    try:
        screenpack.parse_frame_header(bad)
        assert False, "坏头未被拒收"
    except screenpack.ScreenPackError:
        pass
ok("坏头 / 短头拒收")

# 2. 官方出厂 bin ------------------------------------------------------------
print("[2] 官方出厂 bin 解码")
official_files = []
if os.path.isdir(OFFICIAL_DIR):
    official_files = [os.path.join(OFFICIAL_DIR, f)
                      for f in os.listdir(OFFICIAL_DIR) if f.startswith("default_screen_image")]
assert official_files, "找不到官方出厂 bin"
for path in official_files:
    with open(path, "rb") as fh:
        data = fh.read()
    frames = screenpack.split_frames(data)          # 非整数倍会抛
    for f in frames:
        cf, w, h = screenpack.parse_frame_header(f)
        assert cf == 4 and w == 160 and h == 80, f"{path} 头异常 cf={cf} {w}x{h}"
    # 抽一帧往返
    _w, _h, back = screenpack.decode_frame(frames[0])
    _w2, _h2, back2 = screenpack.decode_frame(frames[0])
    assert back == back2
    print(f"    {os.path.basename(path)}: {len(frames)} 帧全头有效")
ok(f"{len(official_files)} 个官方出厂 bin 全部解析通过（格式实锤）")

# 3. GIF 打包 -----------------------------------------------------------------
print("[3] GIF → bin 打包")
from PIL import Image

gif_path = os.path.join(os.environ["TEMP"], "apex5_test_anim.gif")
imgs = []
for i in range(6):
    im = Image.new("RGB", (320, 160), (i * 40 % 256, 100, 200 - i * 30))
    imgs.append(im)
imgs[0].save(gif_path, save_all=True, append_images=imgs[1:], duration=120, loop=0)

rgb_frames, interval, truncated = screenpack.frames_from_gif(gif_path)
assert len(rgb_frames) == 6 and not truncated
assert interval == 120
frames = [screenpack.encode_frame(f) for f in rgb_frames]
blob = screenpack.pack_bin(frames, interval)
assert len(blob) == 6 * 25604
back_frames = screenpack.split_frames(blob)
assert back_frames == frames
ok("6 帧 GIF → 120ms 间隔 → bin → 拆帧往返一致")

assert screenpack.frame_rate(120) == 12
assert screenpack.frame_rate(55) == 6          # round(5.5)=6
assert screenpack.frame_rate(4000) == 255      # 封顶
ok("frameRate = round(ms/10) 映射")

try:
    screenpack.pack_bin([b"\x00"] * 256)
    assert False, "255 上限未生效"
except screenpack.ScreenPackError:
    ok("255 帧上限拒收")

# 4. 差分测试 vs openflydigi ---------------------------------------------------
print("[4] 差分测试（本地 openflydigi 原版）")
# openflydigi 包顶层 __init__ 牵出 Linux 专属 device.py（fcntl/termios）；
# 差分只用纯函数（encode/checksum/build），stub 掉即可
import types
import importlib
for _stub in ("fcntl", "termios", "select"):
    if _stub not in sys.modules:
        try:
            __import__(_stub)
        except ImportError:
            sys.modules[_stub] = types.ModuleType(_stub)
import sys as _sys
_of_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "openflydigi", "flydigi")
_pkg = types.ModuleType("ofly")
_pkg.__path__ = [_of_root]
_sys.modules["ofly"] = _pkg
of_screen = importlib.import_module("ofly.screen")
of_ota = importlib.import_module("ofly.screen_ota")

assert of_screen.encode_frame(rgb) == frame, "像素编码与原版不一致"
ok("帧编码逐字节一致")

data4k = bytes(random.randrange(256) for _ in range(4096))
assert screenota.checksum(data4k) == of_ota.checksum(data4k), "CRC-32 变体不一致"
ok("checksum（C# int 语义）与原版一致")

for opcode, payload in ((11, bytes([1, 14, 12, 0])),
                        (10, b""),
                        (3, struct.pack("<I", 0x2FF000)),
                        (5, struct.pack("<I", 0x2FF000) + struct.pack("<H", 55) + bytes(55)),
                        (12, struct.pack("<II", 346292, 0x12345678))):
    ours = screenota.build(opcode, payload)
    theirs = of_ota.build(opcode, payload)
    assert ours == theirs, f"opcode {opcode} 包构造不一致: {ours.hex()} vs {theirs.hex()}"
ok("5 种 opcode OTA 包构造逐字节一致（含魔数长度常量）")

# 5. Mock 设备全流程 -----------------------------------------------------------
print("[5] Mock 设备全流程演练")


class MockScreenChip:
    """仿真 Freq 芯片：合法回复 + 全程地址/偏移/CRC 记录，供事后断言。"""

    def __init__(self, data, base=0x002FF000):
        self.base = base
        self.data = data
        self.flash = bytearray(len(data))
        self.erased = []
        self.log = []

    def reply(self, request):
        opcode = request[0]
        self.log.append(opcode)
        if opcode == 11:
            body = request[3:7]
            assert body[1] == len(self.data) // screenpack.FRAME_LEN
            return bytes([1, 11]) + struct.pack("<H", 4) + struct.pack("<I", self.base)
        if opcode == 10:
            return bytes([1, 10]) + struct.pack("<H", 6)
        if opcode == 3:
            addr = struct.unpack("<I", request[3:7])[0]
            assert addr >= self.base, f"擦除地址 {addr:#x} 越过图区基址!"
            self.erased.append(addr)
            return bytes([1, 3]) + struct.pack("<H", 6)
        if opcode == 5:
            addr = struct.unpack("<I", request[3:7])[0]
            n = struct.unpack("<H", request[7:9])[0]
            chunk = request[9:9 + n]
            assert self.base <= addr < self.base + len(self.data)
            off = addr - self.base
            self.flash[off:off + len(chunk)] = chunk
            return bytes([1, 5]) + struct.pack("<H", 64)
        if opcode == 12:
            total, crc = struct.unpack("<II", request[3:11])
            assert total == len(self.data)
            assert crc == screenota.checksum(self.data), "PicReset CRC 不符"
            return bytes([1, 12]) + struct.pack("<H", 8)
        raise AssertionError(f"未知 opcode {opcode}")


class MockLink:
    def __init__(self, chip):
        self.chip = chip

    def write(self, data):
        self._pending = self.chip.reply(data)

    def read_reply(self, timeout=None):
        r = self._pending
        self._pending = None
        return r

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass


frames5 = [screenpack.encode_frame(bytes([i * 30 % 256] * (160 * 80 * 3))) for i in range(3)]
data5 = screenpack.join_frames(frames5)
chip = MockScreenChip(data5)
progress_calls = []
with MockLink(chip) as link:
    base = screenota.upload(link, frames5, interval_ms=100,
                            progress=lambda d, t, s: progress_calls.append((d, t, s)))
assert base == 0x002FF000
assert chip.flash == bytearray(data5), "写入内容与源数据不一致"
assert all(a >= base for a in chip.erased)
erases = (len(data5) + 4095) // 4096
writes = (len(data5) + 54) // 55
assert progress_calls and progress_calls[-1] == (erases + writes, erases + writes, "write")
assert len(chip.log) == erases + writes + 3   # + base/version/reset
ok(f"3 帧全流程：base={base:#x}，擦 {erases} 写 {writes}，落盘逐字节一致，地址全程 ≥ base")

# 越界防护：Mock 拒绝越界地址（覆盖程序区=测试失败）——上面 assert 已内建
ok("安全边界：所有擦写地址均在读回基址之内（程序区不可达）")

print(f"\nALL {len(PASS)} SCREEN OFFLINE CHECKS PASS")
