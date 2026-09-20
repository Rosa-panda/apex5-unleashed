# 档案 blob 编辑全家桶（ADR-027，体验区）：turbo / 摇杆曲线 / 扳机行程 / 体感固件层 /
# 握把震动 / 标题 / 四槽快切 / Switch 银行 / 恢复出厂。
# 字节布局全部照抄 openflydigi/mapping.py（原文研读 2026-09-20，ADR-027 D2）：
#   键表 13+id*3 = [target, turbo, freq]；摇杆核心块 109（7B 源形式）+ bank 790
#   （12B，固件只播它）；扳机曲线 123（7B，满量 255）；motion 137（8B）；握把震动 145
#   （9B，反逻辑开关）；data_version 225；标题 770（UTF-16LE 20B）。
# 读写通路走 extkeys.Pad（第二句柄，Windows 多句柄复制输入，与引擎读线程并存）。
import struct
import threading
import time

import extkeys

# ---- 布局常量（openflydigi/mapping.py 同名） ----
OFF_KEY_TABLE = 13
KEY_SLOTS, KEY_ENTRY = 32, 3
OFF_JOYSTICK_CURVE = 109      # 2 x 7：每侧摇杆曲线（源形式）
OFF_TRIGGER_CURVE = 123       # 2 x 7：每侧扳机行程曲线
OFF_MOTION = 137              # 8：体感映射块
OFF_GRIP_VIBRATION = 145      # 9：握把马达
OFF_DATA_VERSION = 225        # LE16
OFF_TITLE = 770               # UTF-16LE x 20
OFF_JOYSTICK_EXTRA = 790      # 2 x 12：type, bank[9], isRound, end
TITLE_BYTES = 20
SWITCH_BANK, SLOTS = 4, 4

CURVE_DEFAULT, CURVE_QUICK, CURVE_SLOW, CURVE_CUSTOM = 0, 1, 2, 3
STICK_PRESETS = {CURVE_DEFAULT: ((63, 63), (127, 127)),
                 CURVE_QUICK: ((64, 96), (127, 127)),
                 CURVE_SLOW: ((64, 32), (127, 127)),
                 CURVE_CUSTOM: None}
BANK_POINTS = 9
CENTER_NOT_A_STICK = 127
BIPOLAR_MAX = 100
ENABLED, DISABLED = 0, 0xFF          # 本 blob 的使能位反逻辑：0=开 0xFF=关

MOTION_OFF, MOTION_LEFT, MOTION_RIGHT, MOTION_MOUSE = 0, 1, 2, 3
MOTION_CLICK, MOTION_PRESS = 0, 1
MOTION_KEY_NONE = 255
MOTION_FPS, MOTION_RACER = 0, 1

TARGET_IDENTITY, TARGET_MACRO, TARGET_KEYBOARD = 255, 32, 254
TURBO_OFF, TURBO_WHILE_HELD, TURBO_TOGGLE = 0, 1, 2

KEY_NAMES = {0: "十字上", 1: "十字右", 2: "十字下", 3: "十字左", 4: "A", 5: "B",
             6: "选择", 7: "X", 8: "Y", 9: "开始", 10: "LB", 11: "RB", 12: "LT",
             13: "RT", 14: "L3", 15: "R3", 16: "C", 17: "Z", 18: "M1", 19: "M2",
             20: "M3", 21: "M4", 22: "M5", 23: "M6", 24: "Fn", 25: "连发",
             27: "Home"}
# k5 可编辑键（GenerateControllerApex5 能力表，C/Z 不在此机型）
APEX5_KEYS = [("a", 4), ("b", 5), ("x", 7), ("y", 8),
              ("十字上", 0), ("十字下", 2), ("十字左", 3), ("十字右", 1),
              ("LB", 10), ("RB", 11), ("LT", 12), ("RT", 13),
              ("L3", 14), ("R3", 15), ("选择", 6), ("开始", 9), ("Home", 27),
              ("M1", 18), ("M2", 19), ("M3", 20), ("M4", 21), ("M5", 22), ("M6", 23)]
SIDE_IDS = {"left": 0, "right": 1}

# Apex 5 出厂档案（openflydigi/factory_config.py，真机读出；四槽仅 774 标题数字不同）
FACTORY_K5 = bytes.fromhex(
    "01034d200428a00000ff000000ff0000ff0000ff0000ff0000ff0000ff0000ff0000"
    "ff0000ff0000ff0000ff0000ff0000ff0000ff0000ff0000ff0000ff0000ff0000ff"
    "0000ff0000ff0000ff0000ff0000ff0000ff0000ff0000ff0000ff0000ff0000ff00"
    "00ff0000ff000000003f3f7f7f7f00003f3f7f7f7f00000000ffffff00000000ffff"
    "ff000c00041914000000003cff320050ff3200011e5005013200ff28780500320001"
    "1e5005013200ff287805003200000000000a0a6401ff460000000000000000000000"
    "0000000a0a6401ff46000000000000000000000000ffffffffff000000000000ffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffff4d916e7f3100000000000000"
    "00000000ffffffff00323e4b5764707d8996000000323e4b5764707d89960000ffff"
    "ffffffff0303030303ffffffffff003f3f7f7f7fffffffff")
TITLE_DIGIT_OFFSET = 774
TITLE_DIGITS = [49, 50, 51, 52]          # 「配置1..4」的数字


def factory_blob(cfg_id):
    """某一槽的出厂档案副本（标题数字换成本槽）。"""
    blob = bytearray(FACTORY_K5)
    blob[TITLE_DIGIT_OFFSET] = TITLE_DIGITS[cfg_id]
    return blob


# ---- 摇杆曲线：源形式 → 九点 bank 编译器（openflydigi 同名函数照抄） ----

def stick_nodes(center=0, edge=0, point1=(63, 63), point2=(127, 127)):
    start = (center, 0) if center > 0 else (0, -center)
    end = (100 - edge, 100) if edge > 0 else (100, 100 + edge)
    scale = 100.0 / 127.0
    span = end[0] - start[0]
    if span <= 0:
        return [start, end]

    def interior(p):
        return (start[0] + span * (p[0] * scale) / 100.0, p[1] * scale)
    return [start, interior(point1), interior(point2), end]


def _along(nodes, x):
    for i in range(len(nodes) - 1):
        (x0, y0), (x1, y1) = nodes[i], nodes[i + 1]
        if x <= x1 or i == len(nodes) - 2:
            if x0 == x1:
                return y0 if x < x0 else y1
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return nodes[-1][1]


def stick_bank(center=0, edge=0, point1=(63, 63), point2=(127, 127)):
    nodes = stick_nodes(center, edge, point1, point2)
    return [int(max(-50, min(100, _along(nodes, 100.0 * i / (BANK_POINTS - 1))))) + 50
            for i in range(BANK_POINTS)]


def _signed(b):
    """center/edge 字节带符号读数：SDK 读端把 >127 折成 127-byte（两写端不一致，
    负值官方读写器自己都对不上——本工具只写 0..100 正值）。"""
    return b if b <= 127 else 127 - b


# ---- 解析 ----

def parse_profile(blob):
    blob = bytes(blob)
    out = {"proto_version": blob[0] | (blob[1] << 8),
           "data_version": blob[OFF_DATA_VERSION] | (blob[OFF_DATA_VERSION + 1] << 8),
           "keys": [], "sticks": {}, "triggers": {}, "motion": {}, "grip_vib": {}}
    try:
        out["title"] = blob[OFF_TITLE:OFF_TITLE + TITLE_BYTES].decode("utf-16le", "ignore").rstrip("\x00")
    except Exception:
        out["title"] = ""
    for name, kid in APEX5_KEYS:
        tgt, turbo, freq = blob[OFF_KEY_TABLE + kid * KEY_ENTRY:
                                OFF_KEY_TABLE + kid * KEY_ENTRY + KEY_ENTRY]
        out["keys"].append({"kid": kid, "name": name, "target": tgt,
                            "target_name": KEY_NAMES.get(tgt, "透传" if tgt == 255 else str(tgt)),
                            "turbo": turbo, "freq": freq})
    for side, sid in SIDE_IDS.items():
        core = blob[OFF_JOYSTICK_CURVE + sid * 7: OFF_JOYSTICK_CURVE + sid * 7 + 7]
        extra = blob[OFF_JOYSTICK_EXTRA + sid * 12: OFF_JOYSTICK_EXTRA + sid * 12 + 12]
        out["sticks"][side] = {
            "type": core[0], "center": _signed(core[1]), "edge": _signed(core[2]),
            "points": [core[3], core[4], core[5], core[6]],
            "is_not_stick": _signed(core[1]) == CENTER_NOT_A_STICK,
            "bank": [b - 50 for b in extra[1:10]], "is_round": extra[10]}
        tc = blob[OFF_TRIGGER_CURVE + sid * 7: OFF_TRIGGER_CURVE + sid * 7 + 7]
        out["triggers"][side] = {"type": tc[0], "zero": tc[1], "end": tc[6],
                                 "points": [tc[2], tc[3], tc[4], tc[5]]}
    m = blob[OFF_MOTION:OFF_MOTION + 8]
    out["motion"] = {"target": m[0], "enable_key": m[1], "enable_type": m[2],
                     "dead_zone": m[3], "sens_x": m[4], "sens_y": m[5],
                     "use_mode": m[6], "enable_key2": m[7]}
    g = blob[OFF_GRIP_VIBRATION:OFF_GRIP_VIBRATION + 9]
    out["grip_vib"] = {"enabled": g[0] == ENABLED,
                       "left": {"on": g[1] == ENABLED, "min": g[2], "max": g[3], "scale": g[4]},
                       "right": {"on": g[5] == ENABLED, "min": g[6], "max": g[7], "scale": g[8]}}
    return out


# ---- 变更（mutate bytearray in place） ----

def set_turbo(blob, kid, mode, freq=10):
    """连发：键表 [target, mode, freq]。turbo 需要真实 target——identity/keyboard/宏
    会被官方强制回 key_id 本身（同款处理，防止连发打在不存在的输出上）。"""
    if mode not in (0, 1, 2):
        raise ValueError("turbo mode")
    off = OFF_KEY_TABLE + kid * KEY_ENTRY
    if mode != TURBO_OFF and blob[off] in (TARGET_IDENTITY, TARGET_KEYBOARD, TARGET_MACRO):
        blob[off] = kid
    blob[off + 1] = mode
    blob[off + 2] = max(1, min(255, int(freq)))
    return blob


def set_stick(blob, side, preset=None, center=0, edge=0, point1=(63, 63),
              point2=(127, 127), is_round=None):
    """摇杆曲线：核心块（源形式）+ 编译 bank 一起写——只写核心块是会动的假滑条
    （固件只播 bank，真机实证）。center/edge 只收 0..100（负值官方读写器编码不一致，拒写）。
    编辑任意参数后 type 一律 CURVE_CUSTOM（官方同款）。"""
    if side not in SIDE_IDS:
        raise ValueError("side")
    if preset is not None and preset not in STICK_PRESETS:
        raise ValueError("preset")
    if preset is not None and STICK_PRESETS[preset] is not None:
        point1, point2 = STICK_PRESETS[preset]
        curve_type = preset
    else:
        curve_type = CURVE_CUSTOM
    center = max(0, min(BIPOLAR_MAX, int(center)))
    edge = max(0, min(BIPOLAR_MAX, int(edge)))
    point1 = (max(0, min(127, int(point1[0]))), max(0, min(127, int(point1[1]))))
    point2 = (max(0, min(127, int(point2[0]))), max(0, min(127, int(point2[1]))))
    sid = SIDE_IDS[side]
    core_off = OFF_JOYSTICK_CURVE + sid * 7
    blob[core_off:core_off + 7] = bytes([curve_type, center, edge,
                                         point1[0], point1[1], point2[0], point2[1]])
    extra_off = OFF_JOYSTICK_EXTRA + sid * 12
    end_byte = blob[extra_off + 11]          # extra 尾字节官方 UI 从不写，原样保留
    if is_round is None:
        is_round = blob[extra_off + 10]
    bank = stick_bank(center, edge, point1, point2)
    blob[extra_off:extra_off + 12] = bytes([curve_type] + bank + [1 if is_round else 0, end_byte])
    return blob


def set_trigger_curve(blob, side, zero, end):
    """扳机行程曲线：zero/end + 线性镜像控制点（官方 UI 唯一产生的组合）。
    出厂 = 0 0 0 0 255 255 255。"""
    if side not in SIDE_IDS:
        raise ValueError("side")
    zero = max(0, min(200, int(zero)))
    end = max(zero + 5, min(255, int(end)))
    span = end - zero
    tc_off = OFF_TRIGGER_CURVE + SIDE_IDS[side] * 7
    blob[tc_off:tc_off + 7] = bytes([blob[tc_off], zero,
                                     zero + span // 3, span // 3,
                                     zero + 2 * span // 3, 2 * span // 3, end])
    return blob


def set_motion(blob, target, enable_key=MOTION_KEY_NONE, enable_type=MOTION_CLICK,
               dead_zone=10, sens_x=50, sens_y=50):
    """体感固件层块（137，8B）。use_mode 由 target 派生：左摇杆=Racer、右摇杆/鼠标=FPS。
    Press 模式才写第二激活键；Click 模式保留原值（出厂 0=十字上，Click 下也是激活键）。"""
    if target not in (MOTION_OFF, MOTION_LEFT, MOTION_RIGHT, MOTION_MOUSE):
        raise ValueError("target")
    enable_type = int(enable_type)
    if enable_type not in (MOTION_CLICK, MOTION_PRESS):
        raise ValueError("enable_type")
    use_mode = MOTION_RACER if target == MOTION_LEFT else MOTION_FPS
    key2 = blob[OFF_MOTION + 7]
    if enable_type == MOTION_PRESS:
        key2 = enable_key
    blob[OFF_MOTION:OFF_MOTION + 8] = bytes([
        target, enable_key, enable_type,
        max(0, min(100, int(dead_zone))),
        max(0, min(100, int(sens_x))), max(0, min(100, int(sens_y))),
        use_mode, key2])
    return blob


def set_grip_vib(blob, enabled, left, right):
    """握把震动块（145，9B）。开关反逻辑：0=开 0xFF=关。min/max 是窗口，写入前排序。"""
    def side_bytes(s):
        lo, hi = sorted((max(0, min(255, int(s.get("min", 0)))),
                         max(0, min(255, int(s.get("max", 255))))))
        return [ENABLED if s.get("on") else DISABLED, lo, hi,
                max(0, min(255, int(s.get("scale", 100))))]
    blob[OFF_GRIP_VIBRATION:OFF_GRIP_VIBRATION + 9] = bytes(
        [ENABLED if enabled else DISABLED] + side_bytes(left or {}) + side_bytes(right or {}))
    return blob


def set_title(blob, text):
    raw = (text or "").encode("utf-16le")[:TITLE_BYTES]
    raw = raw + b"\x00" * (TITLE_BYTES - len(raw))
    blob[OFF_TITLE:OFF_TITLE + TITLE_BYTES] = raw
    return blob


def normalise_for_switch(blob):
    """XInput 档案 → Switch 银行（openflydigi 同名函数语义）：keyboard 目标回透传；
    被映射走的摇杆（center=127 哨兵）回直通摇杆。"""
    for kid in range(KEY_SLOTS):
        off = OFF_KEY_TABLE + kid * KEY_ENTRY
        if blob[off] == TARGET_KEYBOARD:
            blob[off] = TARGET_IDENTITY
    for sid in SIDE_IDS.values():
        core = OFF_JOYSTICK_CURVE + sid * 7
        if _signed(blob[core + 1]) == CENTER_NOT_A_STICK:
            blob[core:core + 7] = bytes([CURVE_DEFAULT, 0, 0, 63, 63, 127, 127])
    return blob


# ---- 会话：全部 Pad 操作串行化 + 读后恢复活跃槽 ----

class ProfileService:
    """档案读写/编辑的唯一入口。extkeys.Pad 每次操作开新句柄，用锁串行。"""

    def __init__(self):
        self._lock = threading.Lock()

    def _read_live(self, pad, cfg_id):
        """读指定槽并把读操作引起的槽切换复原（163 读会把这个槽页成活跃槽）。"""
        blob = pad.read_config(cfg_id)
        pad.apply(cfg_id)
        return blob

    def read_profile(self, cfg_id=None):
        with self._lock:
            pad = extkeys.Pad()
            st = pad.read_status()
            cfg = st["active"] if cfg_id is None else cfg_id
            if not 0 <= cfg < SLOTS:
                raise ValueError("cfg_id")
            blob = self._read_live(pad, cfg)
        return {"slot": cfg, "active": st["active"], **parse_profile(blob)}

    def edit(self, mutator, cfg_id=None):
        """读 → mutator(blob) 原地改 → 写/读回校验/应用/保存。返回新解析。"""
        with self._lock:
            pad = extkeys.Pad()
            st = pad.read_status()
            cfg = st["active"] if cfg_id is None else cfg_id
            if not 0 <= cfg < SLOTS:
                raise ValueError("cfg_id")
            blob = bytearray(pad.read_config(cfg))       # 读即页入，正合写回目标
            old_version = blob[OFF_DATA_VERSION] | (blob[OFF_DATA_VERSION + 1] << 8)
            mutator(blob)
            ver = self._commit(pad, blob, cfg, old_version)
            parsed = parse_profile(blob)
        return {"slot": cfg, "version": ver, **parsed}

    def _commit(self, pad, blob, cfg, old_version):
        """写（全量 42 包）→ 读回校验 → 应用 → 保存（慢，flash）。版本号 +1，
        0xFFFF 视为未写档从 0 起。与 extkeys.ExtKeyMapper._commit 同款（真机已验证）。"""
        ver = 0 if old_version == 0xFFFF else (old_version + 1) & 0xFFFF
        blob[OFF_DATA_VERSION:OFF_DATA_VERSION + 2] = struct.pack("<H", ver)
        packs = [bytes(blob[i:i + extkeys.PKG]) for i in range(0, len(blob), extkeys.PKG)]
        if not any(b[2] == extkeys.CMD_WRITE_START for b in
                   pad.exchange(extkeys.build(extkeys.CMD_WRITE_START,
                                              bytes([cfg, 0, len(packs), extkeys.PKG])))):
            raise RuntimeError("164 写-开始无 ACK")
        for i, p in enumerate(packs):
            if not any(b[2] == extkeys.CMD_WRITE_PACK for b in
                       pad.exchange(extkeys.build(extkeys.CMD_WRITE_PACK, bytes([i]) + p))):
                raise RuntimeError(f"165 包 {i} 无 ACK")
        if bytes(pad.read_config(cfg)) != bytes(blob):
            raise RuntimeError("写后读回不一致")
        if not pad.apply(cfg):
            raise RuntimeError("162 应用无 ACK")
        time.sleep(0.4)
        if not any(b[2] == extkeys.CMD_SAVE for b in
                   pad.exchange(extkeys.build(extkeys.CMD_SAVE, struct.pack("<H", ver)), wait=4.0)):
            raise RuntimeError("166 保存无 ACK（flash 写入慢，属正常失败点，可重试）")
        extkeys.enable_raw_stream(pad)
        return ver

    # ---- 四槽 ----
    def read_slots(self):
        with self._lock:
            pad = extkeys.Pad()
            st = pad.read_status()
            titles, versions = [], st["versions"]
            for i in range(SLOTS):
                blob = self._read_live(pad, i)
                titles.append(parse_profile(blob)["title"])
            return {"active": st["active"], "titles": titles, "versions": versions}

    def apply_slot(self, cfg_id):
        if not 0 <= cfg_id < SLOTS:
            raise ValueError("cfg_id")
        with self._lock:
            pad = extkeys.Pad()
            if not pad.apply(cfg_id):
                raise RuntimeError("162 应用无 ACK")
            extkeys.enable_raw_stream(pad)
        return {"ok": True, "active": cfg_id}

    # ---- Switch 银行 ----
    def sync_switch(self, cfg_id):
        """把 XInput 槽 normalise 后写进对应 Switch 银行槽（+4），再用 171 特殊帧
        落 flash（官方 builder 的 checksum 覆盖范围 bug 字面复刻——「修好」反而无 ACK）。"""
        if not 0 <= cfg_id < SLOTS:
            raise ValueError("cfg_id")
        target = cfg_id + SWITCH_BANK
        with self._lock:
            pad = extkeys.Pad()
            st = pad.read_status()
            blob = bytearray(normalise_for_switch(pad.read_config(cfg_id)))
            ver = (blob[OFF_DATA_VERSION] | (blob[OFF_DATA_VERSION + 1] << 8))
            ver = 1 if ver == 0xFFFF else (ver + 1) & 0xFFFF
            blob[OFF_DATA_VERSION:OFF_DATA_VERSION + 2] = struct.pack("<H", ver)
            packs = [bytes(blob[i:i + extkeys.PKG]) for i in range(0, len(blob), extkeys.PKG)]
            if not any(b[2] == extkeys.CMD_WRITE_START for b in
                       pad.exchange(extkeys.build(extkeys.CMD_WRITE_START,
                                                  bytes([target, 0, len(packs), extkeys.PKG])))):
                raise RuntimeError("164（Switch 槽）写-开始无 ACK")
            for i, p in enumerate(packs):
                if not any(b[2] == extkeys.CMD_WRITE_PACK for b in
                           pad.exchange(extkeys.build(extkeys.CMD_WRITE_PACK, bytes([i]) + p))):
                    raise RuntimeError(f"165 包 {i} 无 ACK")
            pad.apply(st["active"])                    # 读 cfg 页走了活跃槽，复原
            buf = bytearray(32)
            buf[0], buf[1], buf[2], buf[3] = 0x03, 0x5A, 0xA5, 171
            buf[4] = 4
            buf[5], buf[6] = ver & 0xFF, ver >> 8
            buf[7] = target
            buf[8] = sum(buf[3:7]) & 0xFF              # 官方只盖到 7（不含槽字节），照抄
            if not any(b[2] == 171 for b in pad.exchange(bytes(buf), wait=10.0)):
                raise RuntimeError("171 Switch 保存无 ACK")
        return {"ok": True, "switch_slot": target, "version": ver}

    # ---- 恢复出厂 ----
    def factory_reset_slot(self, cfg_id):
        """单槽恢复出厂 = 出厂 blob 写入 + 保存（空间站同款）。注意：不含灯光；
        k5 宏在 blob 里，会一并清掉。"""
        if not 0 <= cfg_id < SLOTS:
            raise ValueError("cfg_id")
        with self._lock:
            pad = extkeys.Pad()
            st = pad.read_status()
            blob = bytearray(pad.read_config(cfg_id))   # 页入目标槽
            old = blob[OFF_DATA_VERSION] | (blob[OFF_DATA_VERSION + 1] << 8)
            fresh = bytearray(factory_blob(cfg_id))
            ver = self._commit(pad, fresh, cfg_id, old)
        return {"ok": True, "slot": cfg_id, "version": ver,
                "was_active": st["active"] == cfg_id}

    def factory_reset_all(self):
        """cmd175：槽字节无效，四槽连名字（blob 内标题）全重置。慢（flash）。"""
        with self._lock:
            pad = extkeys.Pad()
            st = pad.read_status()
            if not any(b[2] == 175 for b in pad.exchange(extkeys.build(175, bytes([0])), wait=12.0)):
                raise RuntimeError("175 无 ACK")
            extkeys.enable_raw_stream(pad)
        return {"ok": True, "was_active": st["active"]}


SERVICE = ProfileService()
