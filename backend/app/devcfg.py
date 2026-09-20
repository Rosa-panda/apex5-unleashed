# 设备设置 + 昵称 + 占用方仲裁（ADR-027，体验区）。
# cmd3 设置块布局 / cmd19-23 写法照抄 openflydigi/settings.py；昵称 cmd2/24 的
# payload 偏移（body[5]）与「无校验和、固件存 len-1 字节」怪癖照抄 identity.py 勘误。
import time

import protocol

NAMES_B0 = ["快切", "XboxHome", "体感去抖", "映射开关", "摇杆防抖", "自动校准", "摇杆回中", "状态栏常亮"]
NAMES_B1 = ["息屏常显", "音频"]
# cmd20 回报率 wire 值 → Hz（k5 实测读回 0=默认，读回 0 时 UI 禁写该项）
RATES = {1: 1000, 2: 500, 4: 250, 8: 125}
# cmd21 精度：wire 值与声明序乱序（值 2 = 10bit）
PRECISIONS = [(0, "默认"), (1, "8bit"), (2, "10bit"), (3, "12bit"), (4, "9bit"),
              (5, "11bit"), (6, "14bit"), (7, "16bit")]
# cmd22 灵敏度：14=Highest .. 20=Lowest 七档
SENSITIVITIES = [(14, "最高"), (15, "较高"), (16, "中高"), (17, "中"), (18, "中低"),
                 (19, "较低"), (20, "最低")]
SLEEP_MAX = 60
NICKNAME_MAX = 26          # 字节（UTF-8），SDK 常量照抄
VERSION_MODULES = ["主控", "接收器", "Switch", "扳机", "屏幕", "ADC", "星闪"]

TAG = b"Apex5Unleashed"


def parse_settings(body):
    """cmd3 回复 body（已剥 report id）→ dict。"""
    if len(body) < 13:
        raise RuntimeError(f"cmd3 回复过短（{len(body)}B）")
    usable, enabled = body[5], body[6]
    return {"flags": {"usable": {n: bool(usable >> i & 1) for i, n in enumerate(NAMES_B0)},
                      "enabled": {n: bool(enabled >> i & 1) for i, n in enumerate(NAMES_B0)},
                      "extra_usable": {n: bool(body[7] >> i & 1) for i, n in enumerate(NAMES_B1)},
                      "extra_enabled": {n: bool(body[8] >> i & 1) for i, n in enumerate(NAMES_B1)}},
            "sleep_min": body[9], "rate": RATES.get(body[10], body[10]),
            "rate_raw": body[10], "precision": body[11], "sensitivity": body[12],
            "raw": body.hex(" ")}


def parse_owner(body):
    """cmd16 回复 → 五开关 + 占用方标签（ASCII 20B，raw 11..30 = body[10..30)）。"""
    if len(body) < 10:
        return None
    out = {"xinput": body[5], "private_data": body[6], "keyboard": body[7],
           "mouse": body[8], "third_party": body[9]}
    if len(body) >= 30:
        tag = bytes(body[10:30]).decode("ascii", "replace").rstrip("\x00 ").strip()
        out["control_by"] = tag or None
    return out


def parse_versions(body):
    """cmd1 心跳 body[15..29)：七模块各 2B BCD（半字节 a.b.c.d），全零 = 模块不存在。"""
    if len(body) < 15 + 2 * len(VERSION_MODULES):
        return None
    out = {}
    for i, name in enumerate(VERSION_MODULES):
        hi, lo = body[15 + 2 * i], body[16 + 2 * i]
        parts = (hi >> 4, hi & 0xF, lo >> 4, lo & 0xF)
        out[name] = ".".join(map(str, parts)) if any(parts) else None
    return out


def nickname_packet(name):
    """cmd24 帧 payload：无校验和（协议 build 本就不带），固件存 buf[4]-1 字节
    → payload = 名字 + 1B 垫。超 26 字节拒绝（截断的名字比报错更糟）。"""
    raw = name.encode("utf-8")
    if not raw or len(raw) > NICKNAME_MAX:
        raise ValueError(f"昵称需 1..{NICKNAME_MAX} 字节（UTF-8）")
    return raw + b"\x00"


def parse_nickname(body):
    """cmd2 回复：payload 在 body[5]（SDK 索引错位勘误）。没起过名的手柄回的不是零
    而是乱字节——可打印性测试照抄 identity.py。"""
    if len(body) < 6:
        return None
    raw = bytes(body[5:]).split(b"\x00", 1)[0].split(b"\xff", 1)[0]
    if not raw or raw[0] in (0x00, 0xFF):
        return None
    try:
        name = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        return None
    return name if name and name.isprintable() else None


def acquire_payload():
    """cmd28 申请仲裁：[23, 1(申请), 20B 标签]。标签表明身份，对方（如空间站）
    可读 cmd16 看到是谁。"""
    return bytes([23, 1]) + TAG


class SettingsWriter:
    """cmd19-23 写 + 读回复核（ACK 回显的是 value 不是 subId，验证必须读回——官方怪癖）。"""

    def __init__(self, engine):
        self.engine = engine

    def _read(self):
        bodies = self.engine.request(protocol.build(protocol.CMD_STATUS), 3, timeout=1.0)
        if not bodies:
            raise RuntimeError("cmd3 无回复（手柄可能休眠）")
        return parse_settings(bodies[-1])

    def read(self):
        return self._read()

    def write_bit(self, sub_id, on):
        """子设置位写（cmd19，sub N = bit N-1；sub 9/10 在 body[8] 那组）。写完读回复核——
        ACK 的 body[5] 回显的是 value 不是 subId，不读回等于没验证（官方怪癖）。"""
        self.engine.send_checked(protocol.build(protocol.CMD_SETTING, bytes([sub_id, 1 if on else 0])),
                                 protocol.CMD_SETTING, source="devcfg")
        time.sleep(0.15)
        return self._read()

    def write_rate(self, wire):
        if wire not in RATES:
            raise ValueError("回报率值非法（k5 读回 0=默认，不可写默认档）")
        self.engine.send_checked(protocol.build(20, bytes([wire])), 20, source="devcfg")
        return self._read()

    def write_precision(self, wire):
        if wire not in {p[0] for p in PRECISIONS}:
            raise ValueError("精度值非法")
        self.engine.send_checked(protocol.build(21, bytes([wire])), 21, source="devcfg")
        return self._read()

    def write_sensitivity(self, wire):
        if wire not in {s[0] for s in SENSITIVITIES}:
            raise ValueError("灵敏度值非法（14..20）")
        self.engine.send_checked(protocol.build(22, bytes([wire])), 22, source="devcfg")
        return self._read()

    def write_sleep(self, minutes):
        minutes = max(0, min(SLEEP_MAX, int(minutes)))
        self.engine.send_checked(protocol.build(23, bytes([minutes])), 23, source="devcfg")
        return self._read()

    def reboot(self):
        self.engine.send_checked(protocol.build(29), 29, source="devcfg")
        return {"ok": True, "note": "手柄重启中，数秒后掉线重连"}
