# 宏功能离线自检（ADR-021 v3.1 宏页方案）：blob 页编码/解析往返 / 校验规则 / 录制器 / Mock 写通路。
# 不碰真机。跑法：backend 下 python test_macro.py
import os
import struct
import sys
import time as _time
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))
os.environ.setdefault("APPDATA", os.path.join(os.environ.get("TEMP", "/tmp"), "apex5_macro_test"))

import extkeys  # noqa: E402
import macro  # noqa: E402

PASS = 0


def check(name, cond):
    global PASS
    if not cond:
        print(f"  ✗ {name}")
        raise AssertionError(name)
    print(f"  ✓ {name}")
    PASS += 1


def section(title):
    print(f"\n[{title}]")


def blank_blob(ver=100):
    """一个像样的 profile blob：proto 3.1 + 数据版本，宏页出厂态（count=0，间隔 3×5）。"""
    b = bytearray(extkeys.PKG * 42)
    b[0:2] = struct.pack("<H", 0x0301)
    b[2] = 77
    b[225:227] = struct.pack("<H", ver)
    b[macro.OFF_MACRO_CYCLE:macro.OFF_MACRO_CYCLE + 5] = b"\x03" * 5
    for kid in range(32):                  # 键表出厂全透传
        b[13 + kid * 3] = 255
    return b


def seq(n):
    """n 个动作的同键按下/抬起交替序列（n 为偶数，收在抬起，配对合法）。"""
    return [{"t": i * 10, "key": 4, "ev": (i + 1) % 2} for i in range(n)]


M1 = {"key_id": 18, "type": 1, "interval": 0, "name": "",
      "actions": [{"t": 10, "key": 4, "ev": 1}, {"t": 50, "key": 4, "ev": 0}]}
M2 = {"key_id": 21, "type": 2, "interval": 250, "name": "",
      "actions": [{"t": 0, "key": 7, "ev": 1}, {"t": 30, "key": 7, "ev": 0},
                  {"t": 60, "key": 7, "ev": 1}, {"t": 90, "key": 7, "ev": 0}]}

# ---------------- 1. 字节级布局 ----------------
section("宏页字节级布局（手算对照，页 @230）")
blob = bytearray(blank_blob())
macro.apply_page(blob, [M1, M2])
page = blob[macro.OFF_MACROS:macro.OFF_MACROS + macro.MACRO_REGION]
check("宏数=2", page[0] == 2)
check("槽0 偏移=0", page[1] == 0)
check("槽1 偏移=3 词（1+2 步）", page[2] == 3)
check("宏1 头 key_id=18", page[6] == 18)
check("宏1 步数=2 LE", page[7:9] == b"\x02\x00")
check("宏1 类型=1(单次)", page[9] == 1)
check("宏1 步1 (10ms→1tick,A,按下)", page[10:14] == struct.pack("<HBB", 1, 4, 1))
check("宏1 步2 (50ms→5tick,A,抬起)", page[14:18] == struct.pack("<HBB", 5, 4, 0))
check("宏2 头 @18 key_id=21 类型=2", page[18] == 21 and page[21] == 2)
check("宏2 步3 (60ms→6tick 累计)", page[30:34] == struct.pack("<HBB", 6, 7, 1))
check("页尾 0xFF 填充", page[38:] == b"\xff" * (macro.MACRO_REGION - 38))
check("间隔字节 槽0=0xFF(未设) 槽1=25(250ms)",
      blob[820] == 0xFF and blob[821] == 25)
check("腾空槽回 0xFF", blob[822:825] == b"\xff" * 3)

# ---------------- 2. 解析往返 ----------------
section("解析往返")
r = macro.parse_page(blob)
check("数据版本透传", r["version"] == 100)
check("宏数量", len(r["macros"]) == 2)
a, b2 = r["macros"]
check("宏1 字段往返", (a["key_id"], a["type"], a["interval"]) == (18, 1, 0))
check("宏1 动作往返（tick×10 还原）",
      a["actions"] == [{"t": 10, "key": 4, "ev": 1}, {"t": 50, "key": 4, "ev": 0}])
check("宏2 间隔往返 250ms", (b2["key_id"], b2["type"], b2["interval"]) == (21, 2, 250))
check("宏2 动作往返", b2["actions"] == M2["actions"])

# ---------------- 3. 出厂态 ----------------
section("出厂态解析（真机只读形态）")
r = macro.parse_page(bytes(blank_blob()))
check("count=0 → 无宏", r["macros"] == [])
factory = bytearray(blank_blob())
factory[macro.OFF_MACROS] = 0xC4            # 真机 172 区看到的垃圾值；页 count 无效同样无宏
check("count=0xC4（无效）→ 无宏", macro.parse_page(factory)["macros"] == [])

# ---------------- 4. 校验规则 ----------------
section("校验规则")
def expect_err(name, macros):
    try:
        macro.apply_page(bytearray(blank_blob()), macros)
        check(name, False)
    except ValueError:
        check(name, True)

expect_err("6 条宏拒绝", [M1] * 6)
expect_err("空动作拒绝", [{**M1, "actions": []}])
expect_err(">64 步/条拒绝", [{**M1, "actions": seq(65)}])
expect_err("按下不配对拒绝", [{**M1, "actions": [{"t": 10, "key": 4, "ev": 1}]}])
expect_err("先抬后按拒绝", [{**M1, "actions": [{"t": 10, "key": 4, "ev": 0}, {"t": 20, "key": 4, "ev": 1}]}])
expect_err("重复按下拒绝", [{**M1, "actions": [{"t": 10, "key": 4, "ev": 1}, {"t": 20, "key": 4, "ev": 1}]}])
expect_err(">655s 拒绝", [{**M1, "actions": [{"t": 0, "key": 4, "ev": 1}, {"t": 655360, "key": 4, "ev": 0}]}])
expect_err("间隔 >2540ms 拒绝", [{**M1, "interval": 2550}])
expect_err("全页 >128 步拒绝", [{**M1, "actions": seq(32)}] * 5)   # 5×32=160 > 128
ok = [{**M1, "actions": seq(24)}] * 5               # 5×24=120 ≤ 128 压线
macro.apply_page(bytearray(blank_blob()), ok)
check("5×24 步压线通过", True)

# ---------------- 5. tick 量化 ----------------
section("10ms tick 量化（逐段量化对齐官方写入器）")
bq = bytearray(blank_blob())
macro.apply_page(bq, [{"key_id": 18, "type": 1, "interval": 0, "name": "",
                       "actions": [{"t": 14, "key": 4, "ev": 1}, {"t": 57, "key": 4, "ev": 0}]}])
page = bq[macro.OFF_MACROS:]
# 段1 14ms→1 tick；段2 间隔 43ms→4 tick → 累计 5
check("逐段量化: 累计 1,5", page[10:12] == b"\x01\x00" and page[14:16] == b"\x05\x00")

# ---------------- 6. 录制器 ----------------
section("录制器（FakeClock）")
clock = {"t": 1000.0}
macro.time = types.SimpleNamespace(monotonic=lambda: clock["t"])   # 仅本测试进程内生效
rec = macro.Recorder()
rec.start()
clock["t"] = 1000.10
rec.feed(1 << 4)                       # A 按下 @100ms
rec.feed(1 << 4)                       # 位图不变 → 无事件
clock["t"] = 1000.25
rec.feed((1 << 4) | (1 << 10) | (1 << 18))   # A 保持 + LB 按下 + M1（拓展键过滤）
clock["t"] = 1000.40
rec.feed(1 << 10)                      # A 抬起 @400ms，LB 保持
acts = rec.stop()["actions"]
check("步数=4（M1 被过滤）", len(acts) == 4)
check("A 按下 @100", acts[0] == {"t": 100, "key": 4, "ev": 1})
check("LB 按下 @250", acts[1] == {"t": 250, "key": 10, "ev": 1})
check("A 抬起 @399（浮点截断）", acts[2] == {"t": 399, "key": 4, "ev": 0})
check("停录自动补 LB 抬起 @399", acts[3] == {"t": 399, "key": 10, "ev": 0})
check("录制态已关", rec.status()["recording"] is False)
check("再 stop 幂等", rec.stop() == {"actions": [], "seconds": 0.0})

clock["t"] = 2000.0                    # 655s 自动封笔
rec.start()
rec.feed(1 << 4)
clock["t"] = 2000.0 + 660.0
rec.feed(0)
check("655s 自动停录", rec.status()["recording"] is False)
macro.time = _time                     # 还原

# ---------------- 7. Mock 写通路 ----------------
section("Mock 写通路（163/164/165/162/166 全流程）")


class MockPad:
    """假 Pad：按命令族回 ACK，165 存包供 163 读回。42 包 840B（同真机 k5）。"""

    def __init__(self, blob=None, corrupt_on_read=False, mute_save=False):
        self.blob = bytearray(blob if blob is not None else blank_blob())
        self.corrupt_on_read = corrupt_on_read
        self.mute_save = mute_save
        self.saved_version = None
        self.applied = 0

    def exchange(self, frame, wait=0.8):
        cmd, n = frame[3], frame[4]
        payload = frame[5:5 + n - 2]
        if cmd == extkeys.CMD_READ:
            out = []
            for i in range(len(self.blob) // extkeys.PKG):
                data = bytes(self.blob[i * extkeys.PKG:(i + 1) * extkeys.PKG])
                if self.corrupt_on_read and i == 12:
                    data = b"\x00" + data[1:]
                out.append(bytes([0x5A, 0xA5, cmd, 42, i, 0]) + data)
            return out
        if cmd == extkeys.CMD_WRITE_START:
            return [bytes([0x5A, 0xA5, cmd, 1])]
        if cmd == extkeys.CMD_WRITE_PACK:
            i = payload[0]
            self.blob[i * extkeys.PKG:(i + 1) * extkeys.PKG] = payload[1:]
            return [bytes([0x5A, 0xA5, cmd, 1])]
        if cmd == extkeys.CMD_APPLY:
            self.applied += 1
            return [bytes([0x5A, 0xA5, cmd, 1])]
        if cmd == extkeys.CMD_SAVE:
            self.saved_version = struct.unpack("<H", payload)[0]
            return [] if self.mute_save else [bytes([0x5A, 0xA5, cmd, 1])]
        if cmd == extkeys.CMD_STATUS:
            return [bytes([0x5A, 0xA5, cmd, 1, 0, 4, 100, 0]) + b"\x00" * 24]
        return []

    def read_status(self):
        return {"active": 0, "versions": [100, 0, 0, 0]}

    def apply(self, cfg):
        self.applied += 1
        return True

    def read_config(self, cfg_id):
        # 走 exchange 的 163 通路拼包（同真机）
        out = bytearray()
        for body in self.exchange(extkeys.build(extkeys.CMD_READ, bytes([cfg_id, extkeys.PKG]))):
            out += body[6:26]
        return out


mock = MockPad()
macro.MANAGER._pad = lambda: mock        # 实例属性遮蔽 staticmethod
out = macro.MANAGER.write([M1, M2])
check("write ok", out["ok"] is True)
check("数据版本自增（100 → 101）", out["version"] == 101)
check("无警告", out["warnings"] == [])
check("apply 调用", mock.applied >= 1)
check("166 保存版本正确", mock.saved_version == 101)
ref = bytearray(blank_blob(0))
macro.apply_page(ref, [M1, M2])
check("固件宏页+间隔=编码结果",
      bytes(mock.blob[macro.OFF_MACROS:macro.OFF_MACROS + macro.MACRO_REGION])
      == bytes(ref[macro.OFF_MACROS:macro.OFF_MACROS + macro.MACRO_REGION])
      and bytes(mock.blob[820:825]) == bytes(ref[820:825]))
check("触发键 M1 键表=32(宏)", mock.blob[13 + 18 * 3] == 32)
check("触发键 M4 键表=32(宏)", mock.blob[13 + 21 * 3] == 32)
check("其余 M 键保持透传", mock.blob[13 + 19 * 3] == 255)
r = macro.MANAGER.read()
check("read 往返", len(r["macros"]) == 2 and r["version"] == 101)
check("写前自动备份落盘", os.path.exists(macro.backup_path()))

# 删除宏 → unbind 还原透传
out = macro.MANAGER.write([M1], unbind=["m4"])
check("删除后 M4 解绑透传", mock.blob[13 + 21 * 3] == 255 and mock.blob[13 + 18 * 3] == 32)

# 166 无 ACK → 降级警告
mock2 = MockPad(mute_save=True)
macro.MANAGER._pad = lambda: mock2
out = macro.MANAGER.write([M1])
check("166 无 ACK → 降级警告不硬失败", out["ok"] is True and len(out["warnings"]) == 1)

# 读回不一致 → 硬失败
mock3 = MockPad(corrupt_on_read=True)
macro.MANAGER._pad = lambda: mock3
try:
    macro.MANAGER.write([M1])
    check("读回不一致硬失败", False)
except RuntimeError as e:
    check("读回不一致硬失败", "不一致" in str(e))

# backup/restore：显式快照 → 改动 → 恢复回快照
macro.MANAGER._pad = lambda: mock2
bk = macro.MANAGER.backup()
check("backup 报告宏数", bk["macros"] == 1)
snap_page = bytes(mock2.blob[macro.OFF_MACROS:macro.OFF_MACROS + macro.MACRO_REGION])
snap_cycle = bytes(mock2.blob[820:825])
macro.MANAGER.write([M1, M2])
out = macro.MANAGER.restore()
check("restore ok", out["ok"] is True)
check("restore 写回快照（宏页+间隔逐字节一致）",
      bytes(mock2.blob[macro.OFF_MACROS:macro.OFF_MACROS + macro.MACRO_REGION]) == snap_page
      and bytes(mock2.blob[820:825]) == snap_cycle)
check("restore 后 M2 键表还原透传", mock2.blob[13 + 21 * 3] == 255)

# ---------------- 8. k5 真机出厂 blob（840B, 宏页 count=0, 间隔 3×5） ----------------
section("k5 真机出厂形态")
k5 = bytearray(extkeys.PKG * 42)
k5[0:2] = b"\x01\x03"          # proto 3.1 LE (769)
k5[2] = 77
k5[225:227] = struct.pack("<H", 55684)   # 真机数据版本
k5[macro.OFF_MACRO_CYCLE:macro.OFF_MACRO_CYCLE + 5] = b"\x03" * 5
r = macro.parse_page(bytes(k5))
check("出厂无宏", r["macros"] == [] and r["version"] == 55684)
mock_k5 = MockPad(blob=k5)
macro.MANAGER._pad = lambda: mock_k5
out = macro.MANAGER.write([M1])
check("出厂直接写 1 条宏 ok", out["ok"] is True)
r = macro.MANAGER.read()
check("写后读回 1 条宏", len(r["macros"]) == 1 and r["macros"][0]["key_id"] == 18)

print(f"\n全部通过：{PASS} 项")
