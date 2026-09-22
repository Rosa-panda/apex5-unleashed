# ADR-032 宏功能离线测试：键表单一所有权 / 宏区作用域拼接 / 宏页读写往返 /
# validate 拒绝项。FakePad 模拟 161-166 命令族，不碰真机。跑法：python test_macro.py
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

import extkeymap
import macro

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


def blank_blob():
    b = bytearray(840)
    b[0:5] = b"\x03\x5a\xa5\xa3\x22"
    b[13 + 18 * 3:13 + 24 * 3] = b"\xff" * 18          # 六拓展键出厂=透传
    b[225:227] = b"\x40\x73"
    return b


class FakePad:
    """161-166 命令族桩：读回即写入态，所有命令回 ACK。"""

    def __init__(self, blob):
        self.blob = bytearray(blob)

    def read_status(self):
        return {"active": 0, "versions": [0] * 4}

    def read_config(self, cfg_id):
        return bytearray(self.blob)

    def apply(self, cfg_id):
        return True

    def exchange(self, frame, wait=0.8):
        cmd = frame[3]
        if cmd == 165:                      # 写包：模拟写入生效（帧[4]=len+2，帧[5]=包序号，帧[6:26]=数据）
            i = frame[5]
            self.blob[i * 20:(i + 1) * 20] = frame[6:26]
        return [bytes([0x5A, 0xA5, cmd]) + bytes(8)]


def mk_macro(key_id=18, actions=None, itv=0, typ=1):
    return {"key_id": key_id, "type": typ, "interval": itv, "name": "",
            "actions": actions or [{"t": 0, "key": 4, "ev": 1},
                                   {"t": 50, "key": 4, "ev": 0}]}


# ---- 裁决规则（纯函数）----
cfg = {"m4": {"mode": "gamepad", "target": 11}, "m2": {"mode": "keyboard", "key": "f"}}
r = macro.resolve_extkey_targets([mk_macro(key_id=20)], cfg)
check("宏键→32", r["m3"] == 32)
check("gamepad 配置保留", r["m4"] == 11)
check("keyboard/未配置→255", r["m2"] == 255 and r["m1"] == 255)
r2 = macro.resolve_extkey_targets([], cfg)
check("删宏后回落配置", r2["m3"] == 255 and r2["m4"] == 11)

# ---- 宏页读写往返（含删除时间隔随宏走）----
blob = blank_blob()
macs = [mk_macro(18, itv=200), mk_macro(20, [{"t": 0, "key": 10, "ev": 1},
                                             {"t": 30, "key": 10, "ev": 0}], itv=60, typ=2)]
macro.apply_page(blob, macs)
got = macro.parse_page(blob)["macros"]
check("两条宏往返", len(got) == 2 and got[0]["key_id"] == 18 and got[1]["key_id"] == 20
      and got[0]["interval"] == 200 and got[1]["type"] == 2
      and got[1]["actions"][1] == {"t": 30, "key": 10, "ev": 0})
del macs[0]
macro.apply_page(blob, macs)
got = macro.parse_page(blob)["macros"]
check("删首条后间隔随宏走", len(got) == 1 and got[0]["key_id"] == 20 and got[0]["interval"] == 60)

try:
    macro.validate([mk_macro(actions=[{"t": 0, "key": 4, "ev": 0}])])
    check("validate 拒先抬后按", False)
except ValueError:
    check("validate 拒先抬后按", True)
try:
    macro.validate([mk_macro()] * 6)
    check("validate 拒超 5 条", False)
except ValueError:
    check("validate 拒超 5 条", True)

# ---- FakePad 全流程：写宏 → 键表所有权 → 删宏回落 ----
tmp = tempfile.mkdtemp()
orig_cfg = extkeymap.cfg_path
orig_bak = macro.backup_path
extkeymap.cfg_path = lambda: os.path.join(tmp, "extkeymap.json")
macro.backup_path = lambda: os.path.join(tmp, "macro_backup.bin")
os.makedirs(tmp, exist_ok=True)
try:
    dev = FakePad(blank_blob())
    macro.MANAGER._pad = lambda: dev        # 实例属性遮蔽类 staticmethod

    res = macro.MANAGER.write([mk_macro(key_id=18)])
    kid18 = 13 + 18 * 3
    check("写宏后 m1 键表=32", dev.blob[kid18] == 32)
    check("写宏后配置归位透传", extkeymap.load()["m1"] == {"mode": "passthrough"})
    check("返回 targets 报告", res["targets"]["m1"] == 32 and res["targets"]["m4"] == 255)
    check("parse 读回一条", len(macro.parse_page(dev.blob)["macros"]) == 1)

    # 映射应用不得踩宏：set_targets 走真 MAPPER+Pad，等价语义在此用裁决规则验证
    check("宏跳过规则", macro.macro_bound_ids(dev.blob) == {18})

    macro.MANAGER.write([])
    check("删宏后 m1 回落 255", dev.blob[kid18] == 255)
    check("删宏后宏页清空", macro.parse_page(dev.blob)["macros"] == [])

    # ---- 宏区作用域拼接 ----
    cur = blank_blob()
    cur[142] = 0x19                                   # 用户调参字节（宏区外）
    bak = bytearray(dev.blob)
    bak[142] = 0xFF                                   # 备份里该字节不同
    spliced = macro.splice_macro_region(bytearray(cur), bak)
    check("拼接保留宏区外字节", spliced[142] == 0x19)
    kid20 = 13 + 20 * 3
    check("拼接带走六键键表项", spliced[kid18:kid18 + 3] == bak[kid18:kid18 + 3]
          and spliced[kid20] == bak[kid20])
    check("拼接带走宏页", spliced[macro.OFF_MACROS:macro.OFF_MACROS + 8] ==
          bytes(bak[macro.OFF_MACROS:macro.OFF_MACROS + 8]))
finally:
    extkeymap.cfg_path = orig_cfg
    macro.backup_path = orig_bak

print()
if failures:
    print(f"{len(failures)} 项失败: {failures}")
    sys.exit(1)
print("全部通过")
