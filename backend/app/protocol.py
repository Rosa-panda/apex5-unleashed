# 协议层：帧构造/解析。规范见 docs/PROTOCOL.md（实机验证 + 官方 SDK 交叉确认）
VID, PID = 0x37D7, 0x2501
USAGE_PAGE_VENDOR = 0xFFA0
REPORT_ID_OUT = 0x03
REPORT_ID_IN = 0x04
PACKET_LEN = 32

CMD_INFO = 0x01
CMD_STATUS = 0x03         # 3：设置块整读（openflydigi settings.py 布局）
CMD_SETTING = 0x13        # 19：子设置写，payload=[sub_id, value]
CMD_RUMBLE = 0x12        # 18
CMD_TRIGGER = 0x51       # 81 SetForceTrigger
CMD_GRIP = 0x52          # 82 SyncWithGrip
CMD_LED_READ = 0xA7      # 167 ReadLedConfig（多包 ACK）
CMD_LED_WRITE_START = 0xA8   # 168 WriteRgb Start
CMD_LED_WRITE_PACK = 0xA9    # 169 WriteRgb Pack（20B/包）
CMD_LED_TEST = 0xF5      # 245 TestLed：直接点色

SIDE = {"left": 1, "right": 2}

# 0xEF 位图 32 键全名（ControllerKey 枚举，id 与键表/宏 blob 同源；ADR-021 录制 UI 用）
KEY32_NAMES = {0: "十字上", 1: "十字右", 2: "十字下", 3: "十字左", 4: "A", 5: "B", 6: "选择",
               7: "X", 8: "Y", 9: "开始", 10: "LB", 11: "RB", 12: "LT", 13: "RT",
               14: "L3", 15: "R3", 16: "C", 17: "Z", 18: "M1", 19: "M2", 20: "M3",
               21: "M4", 22: "M5", 23: "M6", 24: "Fn", 25: "连发", 27: "Home"}

# 六模式参数布局（官方 SetForceTriggerCommandFactory 反编译，钳位照抄）
TRIGGER_MODES = {
    "normal":    dict(fields=[]),
    "race":      dict(fields=[("stroke", 1, 255), ("resistance", 1, 255), ("match", 0, 1)]),
    "sniper":    dict(fields=[("stroke", 1, 255), ("press", 1, 255), ("strength", 1, 255), ("freq", 1, 255), ("match", 0, 1)]),
    "recoil":    dict(fields=[("stroke", 1, 255), ("recoil_stroke", 1, 255), ("strength", 1, 255), ("match", 0, 1)]),
    "lock":      dict(fields=[("stroke", 1, 255), ("strength", 1, 255), ("match", 0, 1)]),
    "vibration": dict(fields=[("stroke", 1, 255), ("press", 1, 255), ("strength", 1, 255), ("freq", 1, 255), ("match", 0, 1)]),
}
GRIP_FIELDS = [("filter", 0, 255), ("scale", 0, 255), ("stroke", 0, 255),
               ("press", 0, 255), ("strength", 0, 255), ("freq", 0, 255)]


def clamp(v, lo, hi):
    return max(lo, min(hi, int(v)))


def build(cmd, payload=b""):
    """32B 输出帧。81/82/18 官方本就不写校验和（PROTOCOL.md）。"""
    buf = bytearray(PACKET_LEN)
    buf[0] = REPORT_ID_OUT
    buf[1] = 0x5A
    buf[2] = 0xA5
    buf[3] = cmd
    buf[4] = len(payload)
    buf[5:5 + len(payload)] = payload
    return bytes(buf)


def ack_ok(body, cmd_id):
    """body = 已剥 report id 的帧。成功位 [3]（非 K6 家族）。"""
    return len(body) > 3 and body[2] == cmd_id and body[3] == 1


def trigger_payload(apply, side, mode, params):
    """cmd 81 payload（帧 [5] 起）。返回 None 表示参数非法。"""
    spec = TRIGGER_MODES.get(mode)
    if spec is None or side not in SIDE.values():
        return None
    values = [clamp(params.get(f[0]), f[1], f[2]) if params.get(f[0]) is not None else f[1]
              for f in spec["fields"]]
    mode_id = list(TRIGGER_MODES).index(mode)
    return bytes([1 if apply else 0, side, mode_id] + values)


def grip_payload(side, params):
    """cmd 82 payload：[side, bindType=2, filter, scale, stroke, press, strength, freq]"""
    values = [clamp(params.get(f[0]), f[1], f[2]) if params.get(f[0]) is not None else 0
              for f in GRIP_FIELDS]
    return bytes([side, 2] + values)


def mock_ack_frame(cmd_id):
    """MockPad 伪造的 ACK 输入报告（含 report id 0x04 前缀）。
    cmd1 心跳特例：body[11]=0x04（电量 4/5），Mock 模式 UI 也有电量可显示。"""
    if cmd_id == CMD_INFO:
        # 与真机回复同布局：body[5]=0x80 设备类型，body[7..10]=MAC，body[11]=电量
        return bytes([REPORT_ID_IN, 0x5A, 0xA5, cmd_id, 0x01, 0x00, 0x80] + [0] * 5 + [0x04] + [0] * 19)
    return bytes([REPORT_ID_IN, 0x5A, 0xA5, cmd_id, 0x01, 0x00, 0x80] + [0] * 25)


# ---------------- 灯光协议（ADR-018：官方 WriteRgbConfigCommand / LedConfigParser 反编译） ----------------
# 官方 SDK 帧带累加和 CRC：len[4] = cmd 起到 CRC 前的字节数（= payload + 2），CRC = sum(frame[3:3+len]) & 0xFF
LED_PACK_SIZE = 20
LED_TYPES = {"off": 6, "on": 5, "breath": 2, "gradient": 3, "flow": 1, "default": 7}
LED_MODE_PROTO = {"off": 0, "on": 1, "smart": 2}


def crc8_sum(data):
    """官方 ByteExtension.Crc：8 位累加和。"""
    return sum(data) & 0xFF


def build_crc(cmd, payload):
    """带 CRC 的输出帧（灯光族命令用官方 CRC 封装；51/82/18 官方本就不带校验）。补零到 32B 报告。"""
    n = len(payload) + 2                     # cmd 字节 + len 字节 + payload
    buf = bytearray([REPORT_ID_OUT, 0x5A, 0xA5, cmd, n]) + bytearray(payload)
    buf.append(crc8_sum(buf[3:3 + n]))
    return bytes(buf.ljust(PACKET_LEN, b"\x00"))


def led_test_frame(r, g, b):
    """0xF5：工厂测试直点色（探针首选，最安全）。"""
    return build_crc(CMD_LED_TEST, bytes([clamp(r, 0, 255), clamp(g, 0, 255), clamp(b, 0, 255)]))


def led_read_frame(cfg_id=0):
    """0xA7：读灯表。pkgSize 固定 20。"""
    return build_crc(CMD_LED_READ, bytes([cfg_id, LED_PACK_SIZE]))


def led_write_start_frame(cfg_id, packet_num, packet_size=LED_PACK_SIZE):
    """0xA8：通知固件开始接收。"""
    return build_crc(CMD_LED_WRITE_START,
                     bytes([cfg_id, 0, packet_num & 0xFF, packet_size]))


def led_write_pack_frame(pack_num, pack):
    """0xA9：写一个 ≤20B 数据包。"""
    pack = bytes(pack[:LED_PACK_SIZE])
    return build_crc(CMD_LED_WRITE_PACK, bytes([pack_num]) + pack)


def parse_led_bean(data):
    """灯表 blob → dict（LedConfigParser V2/V3）。data = 多包 ACK 数据段的顺序拼接（无 5A A5 前缀）。
    布局：[0]=ver&0xF [1]=ver>>8 [2]=clickFeedback [3]=loopStart [4]=loopEnd [5]=loopTime
          [6]=brightness [7]=rgbNum [8]=ledMode [9]=gripSync(V3) [10..]=保留/帧数据"""
    if len(data) < 20 or data[1] not in (2, 3):
        return None
    bean = {"version": data[1], "click_feedback": data[2], "loop_start": data[3],
            "loop_end": data[4], "loop_time": data[5], "brightness": data[6],
            "rgb_num": data[7], "led_mode": data[8],
            "raw_version_bytes": (data[0], data[1])}
    bean["grip_sync"] = data[9] if data[1] == 3 else None
    return bean


def led_bean_header(bean, frames_b):
    """bean dict + 帧数据 → 完整 blob（保持真机读回的版本字节/保留区原样）。"""
    v_lo, v_hi = bean.get("raw_version_bytes", (0, 2))
    head = bytearray(20)
    head[0], head[1] = v_lo, v_hi
    head[2] = bean.get("click_feedback", 0) & 0xFF
    head[3] = bean.get("loop_start", 0) & 0xFF
    head[4] = bean.get("loop_end", 0) & 0xFF
    head[5] = bean.get("loop_time", 10) & 0xFF
    head[6] = bean.get("brightness", 128) & 0xFF
    head[7] = bean.get("rgb_num", 0) & 0xFF
    head[8] = bean.get("led_mode", 1) & 0xFF
    if bean.get("version") == 3:
        head[9] = (1 if bean.get("grip_sync") else 0) & 0xFF
        head[10:20] = b"\xff" * 10
    else:
        head[9:20] = b"\xff" * 11
    return bytes(head) + bytes(frames_b)


def led_frames_solid(rgb, rgb_num):
    return bytes(bytearray(list(rgb) * rgb_num))


def led_frames_breath(rgb, rgb_num, steps=16):
    """呼吸：0→峰值→0 的线性 ramp（官方曲线未知，先用线性，后续可抄 0xA7 读回的官方帧表）。"""
    out = bytearray()
    half = max(2, steps // 2)
    ramp = [round(255 * i / half) for i in range(half + 1)] + \
           [round(255 * i / half) for i in range(half - 1, 0, -1)]
    for v in ramp:
        out.extend(bytearray([c * v // 255 for c in rgb] * rgb_num))
    return bytes(out)


def led_frames_gradient(colors, rgb_num, steps=16):
    """渐变：多色间线性插值。colors=[(r,g,b), ...] ≥2。"""
    out = bytearray()
    for i in range(steps):
        t = i / (steps - 1) * (len(colors) - 1)
        j = min(int(t), len(colors) - 2)
        f = t - j
        c0, c1 = colors[j], colors[j + 1]
        rgb = tuple(round(c0[k] + (c1[k] - c0[k]) * f) for k in range(3))
        out.extend(bytearray(list(rgb) * rgb_num))
    return bytes(out)


def led_frames_flow(colors, rgb_num, steps=16):
    """流光：色相沿灯珠位置流动（每帧整体平移相位）。"""
    out = bytearray()
    n = max(1, len(colors))
    for i in range(steps):
        frame = bytearray()
        for led in range(rgb_num):
            t = ((led / rgb_num) + i / steps) % 1.0 * n
            j = min(int(t), n - 1)
            f = t - j
            c0, c1 = colors[j % n], colors[(j + 1) % n]
            rgb = tuple(round(c0[k] + (c1[k] - c0[k]) * f) for k in range(3))
            frame.extend(rgb)
        out.extend(frame)
    return bytes(out)
