# 协议层：帧构造/解析。规范见 docs/PROTOCOL.md（实机验证 + 官方 SDK 交叉确认）
import math

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

# 六模式参数布局（官方 SetForceTriggerCommandFactory 反编译，钳位照抄）。
# ⚠ 2026-09-20 勘误（ADR-022，依据 ApexSenseBridge 实测）：固件 wire 枚举 2/3 与官方
# SDK 字面名相反——wire2 实际手感=后坐力回弹，wire3=狙击突破。字段布局跟 wire 走，
# 名字按真实手感标注（待实机复核，若推翻回滚本交换即可）。
TRIGGER_MODES = {
    "normal":    dict(fields=[]),
    "race":      dict(fields=[("stroke", 1, 255), ("resistance", 1, 255), ("match", 0, 1)]),
    "recoil":    dict(fields=[("stroke", 1, 255), ("press", 1, 255), ("strength", 1, 255), ("freq", 1, 255), ("match", 0, 1)]),   # wire2（原误标 sniper）
    "sniper":    dict(fields=[("stroke", 1, 255), ("recoil_stroke", 1, 255), ("strength", 1, 255), ("match", 0, 1)]),            # wire3（原误标 recoil）
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


def _hsv_to_rgb(h, s, v):
    """h∈[0,360) s/v∈[0,1] → (r,g,b) 0-255（彩虹灯效用）。"""
    c = v * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = v - c
    seg = int(h // 60) % 6
    rp = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][seg]
    return tuple(round((ch + m) * 255) for ch in rp)


def led_frames_blink(rgb, rgb_num, repeats=2):
    """闪烁：亮/灭方波（帧数少，节奏由 loop_time 控制）。"""
    on = bytearray(list(rgb) * rgb_num)
    off = bytearray(rgb_num * 3)
    return bytes((on + off) * max(1, repeats))


def led_frames_heartbeat(rgb, rgb_num):
    """心跳：强搏-歇-弱搏-长歇的双峰包络（12 帧）。"""
    env = (0.0, 1.0, 0.55, 0.0, 0.0, 0.6, 0.3, 0.0, 0.0, 0.0, 0.0, 0.0)
    out = bytearray()
    for k in env:
        frame = bytearray()
        for _ in range(rgb_num):
            frame.extend(round(c * k) for c in rgb)
        out.extend(frame)
    return bytes(out)


def led_frames_wipe(colors, rgb_num):
    """扫描：逐珠点亮到全亮再逐珠熄灭（2×rgb_num 帧）。
    注意：fill+fill[::-1] 在拼接点把全亮帧/单灯帧各重复一次——光到头滞留一拍、
    循环末一盏灯多亮一拍才开下一轮（ADR-033 记录的观感瑕疵，原版保留不改）。"""
    c = tuple(colors[0])
    fill = []
    for k in range(rgb_num):
        frame = bytearray()
        for i in range(rgb_num):
            frame.extend(c if i <= k else (0, 0, 0))
        fill.append(bytes(frame))
    return bytes(b"".join(fill + fill[::-1]))


def led_frames_comet(colors, rgb_num):
    """扫描·循环（ADR-033 修订，wipe 的修复复刻版）：逐珠点亮，跑满整条灯带后
    直接从头开始。帧序 = 亮 1,2,…,rgb_num 珠（n 帧），无排空半程、无重复驻留帧。
    原版扫描（led_frames_wipe）跑满后倒序退光，且拼接点重复帧造成「右边留光
    赖着不走才开下一轮」的观感——本版跑满瞬间回表首，零残留。"""
    c = tuple(colors[0])
    out = bytearray()
    for k in range(rgb_num):
        frame = bytearray()
        for i in range(rgb_num):
            frame.extend(c if i <= k else (0, 0, 0))
        out.extend(frame)
    return bytes(out)


def led_frames_duosweep(colors, rgb_num):
    """双色对扫（ADR-033 修订 4）：colors[0] 从左往右、colors[1] 从右往左相向
    逐珠铺满；相遇瞬间两色前端融合（相互影响，不再是硬切边）；铺满后全黑
    喘息两拍再重开——否则两端全循环常亮（右端孤色观感为「永不熄灭」）。
    帧数 = ceil(rgb_num/2) + 2。"""
    ca = tuple(colors[0])
    cb = tuple(colors[1 % len(colors)])
    mix = tuple((a + b) // 2 for a, b in zip(ca, cb))
    steps = (rgb_num + 1) // 2
    out = bytearray()
    for k in range(steps):
        met = (rgb_num - 1 - k) - k <= 1        # 两前端已相邻/重叠（最后一拍）
        frame = bytearray()
        for i in range(rgb_num):
            li = i <= k                         # 左色向右推进
            ri = i >= rgb_num - 1 - k           # 右色向左推进
            if (li and ri) or (met and (i == k or i == rgb_num - 1 - k)):
                frame.extend(mix)               # 相遇处两色融合
            elif li:
                frame.extend(ca)
            elif ri:
                frame.extend(cb)
            else:
                frame.extend((0, 0, 0))         # 中缝随帧收窄
        out.extend(frame)
    for _ in range(2):                          # 表尾喘息拍：两端每轮真正熄灭一次
        out.extend(bytes(rgb_num * 3))
    return bytes(out)


def led_frames_rain(colors, rgb_num, tail=3):
    """彗星雨（ADR-033 修订 3）：亮头带拖尾连续掠过，一颗接一颗不断档。
    步数 = rgb_num + tail，跨循环处旧尾未散新头已入，观感为连绵流星。"""
    c = tuple(colors[0])
    steps = rgb_num + tail
    out = bytearray()
    for p in range(steps):                      # p=光头位置
        frame = bytearray()
        for i in range(rgb_num):
            d = p - i
            if 0 <= d <= tail:
                s = (tail + 1 - d) / (tail + 1)
                frame.extend(round(v * s) for v in c)
            else:
                frame.extend((0, 0, 0))
        out.extend(frame)
    return bytes(out)


def led_frames_chase(colors, rgb_num, steps=None):
    """双色追及（ADR-033 修订 3）：两色同向绕圈，色 B 三倍速追色 A，
    分界线随两速差持续游走。步数 = rgb_num。"""
    ca, cb = tuple(colors[0]), tuple(colors[1 % len(colors)])
    steps = steps or rgb_num
    out = bytearray()
    for k in range(steps):
        pa, pb = k % rgb_num, (k * 3) % rgb_num
        frame = bytearray()
        for i in range(rgb_num):
            da = min((i - pa) % rgb_num, (pa - i) % rgb_num)
            db = min((i - pb) % rgb_num, (pb - i) % rgb_num)
            frame.extend(ca if da <= db else cb)      # 环上就近归属
        out.extend(frame)
    return bytes(out)


def led_frames_pulse(colors, rgb_num):
    """中心脉冲（ADR-033 修订 3）：从中心向两端炸开再收回，像能量搏动。
    步数 = 2×ceil(n/2)-1，铺满帧在正中。"""
    c = tuple(colors[0])
    hi = (rgb_num + 1) // 2
    radii = list(range(1, hi + 1)) + list(range(hi - 1, 0, -1))
    out = bytearray()
    for r in radii:
        frame = bytearray()
        for i in range(rgb_num):
            frame.extend(c if hi - r <= i < hi + r else (0, 0, 0))
        out.extend(frame)
    return bytes(out)


def led_frames_fire(colors, rgb_num, steps=16):
    """火苗（ADR-033 修订 3）：逐珠独立明暗抖动。用确定性伪噪声（双正弦积，
    无缝循环）而非随机数——同参数可复现，识别可逐点校验。"""
    c = tuple(colors[0])
    out = bytearray()
    for k in range(steps):
        frame = bytearray()
        for i in range(rgb_num):
            n1 = math.sin(2.399 * i + 2 * math.pi * k / steps)
            n2 = math.sin(1.7 * i + 2.4 + 2 * math.pi * 3 * k / steps)
            s = 0.3 + 0.7 * ((n1 * n2 + 1) / 2)
            frame.extend(round(v * s) for v in c)
        out.extend(frame)
    return bytes(out)


def led_frames_auroraflow(colors, rgb_num, steps=24):
    """呼吸流光（ADR-033 修订 3）：空间色相流动 + 快起慢落呼吸 + 行进高光带，
    三层叠加。步数 = 24。"""
    cs = [tuple(c) for c in (colors if len(colors) >= 2 else [(0, 255, 180), (60, 0, 255)])]
    m = len(cs)
    out = bytearray()
    for k in range(steps):
        u = k / steps
        e = u / 0.3 if u < 0.3 else 1 - (u - 0.3) / 0.7          # 快起慢落包络
        glow = 0.35 + 0.65 * e
        band = u * rgb_num                                        # 高光带中心行进
        frame = bytearray()
        for i in range(rgb_num):
            x = (i / rgb_num + u) % 1 * m
            j = int(x) % m
            rgbv = [a + (b - a) * (x - int(x)) for a, b in zip(cs[j], cs[(j + 1) % m])]
            dd = min(abs(i - band), abs(i - band + rgb_num), abs(i - band - rgb_num))
            hl = 1 + 0.6 * math.exp(-(dd / 1.5) ** 2)
            frame.extend(round(min(255, v * glow * hl)) for v in rgbv)
        out.extend(frame)
    return bytes(out)


def led_frames_typewriter(colors, rgb_num):
    """打字机（ADR-033 修订 3）：逐珠点亮铺满后末珠闪两下再熄，像发送完成回执。
    步数 = rgb_num + 5。"""
    c = tuple(colors[0])
    seq = list(range(1, rgb_num + 1)) + [rgb_num - 1, rgb_num, rgb_num - 1, rgb_num, 0]
    out = bytearray()
    for lit_n in seq:
        frame = bytearray()
        for i in range(rgb_num):
            frame.extend(c if i < lit_n else (0, 0, 0))
        out.extend(frame)
    return bytes(out)


def led_frames_rainbow(rgb_num, steps=24, sat=1.0, val=0.55):
    """彩虹循环：色相环沿灯珠分布并随帧旋转（不依赖 colors）。"""
    out = bytearray()
    for s in range(steps):
        frame = bytearray()
        for led in range(rgb_num):
            h = ((led / rgb_num) + s / steps) % 1.0 * 360
            frame.extend(_hsv_to_rgb(h, sat, val))
        out.extend(frame)
    return bytes(out)


def led_frames_aurora(colors, rgb_num, steps=24):
    """极光：空间多色渐变随帧缓慢流动 + 全局正弦明暗（呼吸感+流动感叠加）。"""
    cs = [tuple(c) for c in (colors if len(colors) >= 2 else [(0, 255, 180), (60, 0, 255)])]
    n = len(cs)
    out = bytearray()
    for s in range(steps):
        glow = 0.55 + 0.45 * math.sin(s / steps * 2 * math.pi)
        frame = bytearray()
        for led in range(rgb_num):
            t = ((led / rgb_num) + s / steps) % 1.0 * n
            j = int(t) % n
            f = t - int(t)
            c0, c1 = cs[j], cs[(j + 1) % n]
            frame.extend(round((c0[k] + (c1[k] - c0[k]) * f) * glow) for k in range(3))
        out.extend(frame)
    return bytes(out)


# ---------------- 灯效识别（帧表 → 模式+配色反推，供进页还原上次设置） ----------------

def _close_rgb(a, b, tol=8):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def _collinear(a, b, c, tol=7):
    """颜色 b 是否近似落在 a→c 的线段上（gradient 拐点检测用）。"""
    u = [y - x for x, y in zip(b, a)]
    v = [y - x for x, y in zip(c, a)]
    cross = (u[1] * v[2] - u[2] * v[1],
             u[2] * v[0] - u[0] * v[2],
             u[0] * v[1] - u[1] * v[0])
    length = math.sqrt(sum(x * x for x in v))
    if length < 1e-6:
        return True
    return math.sqrt(sum(x * x for x in cross)) / length < tol


def _hue_of(c):
    """(r,g,b) 0-255 → 色相 0-360；灰阶返回 None。"""
    r, g, b = (x / 255 for x in c)
    mx, mn = max(r, g, b), min(r, g, b)
    if mx == mn or mx == 0:
        return None
    if mx == r:
        h = ((g - b) / (mx - mn)) % 6
    elif mx == g:
        h = (b - r) / (mx - mn) + 2
    else:
        h = (r - g) / (mx - mn) + 4
    return h * 60


def led_identify(blob):
    """灯表 blob（20B 头 + 帧数据）→ 尽力识别当前灯效。
    返回 {"mode", "colors": [[r,g,b],...], "known": bool}。
    mode ∈ off/on/breath/gradient/flow/blink/heartbeat/wipe/comet/rainbow/aurora/unknown。
    判定顺序按歧义度从高到低：全灭 → 整帧同色系(blink→标量族 on/breath/heartbeat→gradient)
    → wipe(前缀亮) → rainbow(色相沿珠分布) → flow(帧间循环平移) → aurora(兜底空间系)。
    官方/第三方灯效若模式超出已知集合，known=False 原样告知（UI 只读展示，不乱写）。"""
    unknown = {"mode": "unknown", "colors": [], "known": False}
    bean = parse_led_bean(blob)
    if bean is None:
        return unknown
    n = bean["rgb_num"]
    body = blob[20:]
    if n <= 0 or len(body) < n * 3:
        return unknown
    nf = len(body) // (n * 3)
    # [帧][灯珠](r,g,b)
    fr = [[tuple(body[i * n * 3 + j * 3: i * n * 3 + j * 3 + 3]) for j in range(n)]
          for i in range(nf)]
    # 只看 loop 范围内的帧：固件槽位尾部常残留旧表的帧（擦不掉），混进来会让
    # 识别必然失败（ADR-033 修订 3 修复「自己写的灯效被认成外部灯效」）。
    ls, le = bean["loop_start"], bean["loop_end"]
    if 0 <= le < nf:
        fr = fr[max(0, ls): le + 1]
        nf = len(fr)

    # 1) 全灭
    if all(all(c == (0, 0, 0) for c in f) for f in fr):
        return {"mode": "off", "colors": [], "known": True}

    def uniform(f):
        return all(c == f[0] for c in f)

    # 2) 整帧同色系（temporal：on/blink/breath/heartbeat/gradient）
    if all(uniform(f) for f in fr):
        base = [f[0] for f in fr]
        distinct = []
        for c in base:
            if not any(_close_rgb(c, d) for d in distinct):
                distinct.append(c)
        # blink：恰两态且其一为纯黑
        if len(distinct) == 2 and any(all(ch == 0 for ch in d) for d in distinct):
            c = next(d for d in distinct if any(ch != 0 for ch in d))
            return {"mode": "blink", "colors": [list(c)], "known": True}
        # 标量族：全部帧都是同一颜色 × 系数 → on（常数）/ breath（单峰）/ heartbeat（双峰）
        peak = max(base, key=lambda c: max(c))

        def scale_of(c):
            ks = []
            for p, x in zip(peak, c):
                if p == 0:
                    if x != 0:
                        return None
                    ks.append(1.0)
                else:
                    ks.append(x / p)
            if all(abs(k - ks[0]) < 0.08 for k in ks):
                return ks[0]
            return None

        scales = [scale_of(c) for c in base]
        if all(s is not None for s in scales):
            if len(distinct) == 1:
                return {"mode": "on", "colors": [list(distinct[0])], "known": True}
            peaks = sum(1 for i in range(1, len(scales) - 1)
                        if scales[i] >= scales[i - 1] and scales[i] >= scales[i + 1]
                        and scales[i] > 0.15)
            return {"mode": "heartbeat" if peaks >= 2 else "breath",
                    "colors": [list(peak)], "known": True}
        # temporal 多色 → gradient：找插值拐点还原原配色（线性分段插值的顶点）
        pal = [list(base[0])]
        for i in range(1, nf - 1):
            if not _collinear(base[i - 1], base[i], base[i + 1]):
                pal.append(list(base[i]))
        pal.append(list(base[-1]))
        pal = [p for i, p in enumerate(pal)
               if not any(_close_rgb(p, q, 10) for q in pal[:i])]
        if len(pal) >= 2:
            return {"mode": "gradient", "colors": pal[:5], "known": True}
        return unknown

    # 3) wipe：每帧都是「前缀亮 + 其余黑」，且亮珠数在变（0..n..0）
    lit = [sum(1 for c in f if max(c) > 8) for f in fr]

    def is_prefix(f):
        on = True
        for c in f:
            if max(c) > 8:
                if not on:
                    return False
            else:
                on = False
        return True

    # 3) comet（扫描·循环，ADR-033）：全前缀帧且亮珠数恰为 1,2,…,n 帧数——
    #    跑满即回表首循环。原版扫描（wipe）亮珠数会到 n 再退回（先增后减），
    #    且必带倒序半程，由此区分；须先于 wipe 判定。
    if all(is_prefix(f) for f in fr) and lit == list(range(1, len(fr) + 1)):
        c = next(fr[i][0] for i, k in enumerate(lit) if k > 0)
        return {"mode": "comet", "colors": [list(c)], "known": True}

    # 3.1) typewriter（打字机，ADR-033 修订 3）：全前缀帧，亮珠数 = 1..n 铺满后
    #      末珠闪两下（n-1,n,n-1,n）再全灭。须先于 wipe 判定（帧形同为前缀）。
    if all(is_prefix(f) for f in fr) and lit == list(range(1, n + 1)) + [n - 1, n, n - 1, n, 0]:
        c = next(fr[i][0] for i, k in enumerate(lit) if k > 0)
        return {"mode": "typewriter", "colors": [list(c)], "known": True}

    if all(is_prefix(f) for f in fr) and len(set(lit)) >= 3:
        c = next(fr[i][0] for i, k in enumerate(lit) if k > 0)
        return {"mode": "wipe", "colors": [list(c)], "known": True}

    # 3.5) duosweep（双色对扫，ADR-033 修订 4）：每帧两端同亮，左段一色右段另一色、
    #      中缝随帧收窄至会合铺满（相遇拍两前端为混色）；表尾允许全黑喘息拍。
    #      wipe 单端起扫、flow 全帧渐变过渡，均不会误入。
    a0, b0 = fr[0][0], fr[0][-1]
    if not _close_rgb(a0, b0, 10):
        mx = tuple((a + b) // 2 for a, b in zip(a0, b0))
        body_duo = fr[:]
        while body_duo and all(c == (0, 0, 0) for c in body_duo[-1]):
            body_duo.pop()                       # 剥掉表尾喘息拍（全黑帧）
        if not body_duo:
            body_duo = fr

        def is_duo(f):
            on = [j for j, c in enumerate(f) if max(c) > 8]
            if not on or on[0] != 0 or on[-1] != n - 1:
                return False                   # 两端必须都亮
            j = 0
            while j < n and _close_rgb(f[j], a0, 30):
                j += 1                          # 左段 = A 色
            seen_b = False
            for t in range(j, n):
                if _close_rgb(f[t], b0, 30):
                    seen_b = True               # 右段 = B 色（须连续贴右端）
                elif not seen_b and _close_rgb(f[t], mx, 30):
                    pass                        # 相遇拍融合色（介于 A/B 之间）
                elif any(f[t]) or seen_b:
                    return False                # 中缝只许全黑，且不许在 B 段后再断
            return True
        if all(is_duo(f) for f in body_duo):
            return {"mode": "duosweep", "colors": [list(a0), list(b0)], "known": True}

    # 3.6) rain（彗星雨，ADR-033 修订 3）：每帧一段连续 run、左右两半都出现过
    #      独立 run（光头过境）、起点单调推进、run 长度受限——pulse 的居中 run、
    #      fire/chase 的全亮帧都不会误入。
    def _run2(f):
        on = [j for j, c in enumerate(f) if max(c) > 8]
        if not on:
            return None
        return (on[0], on[-1]) if on[-1] - on[0] + 1 == len(on) else ()

    runs2 = [_run2(f) for f in fr]
    if () not in runs2 and None not in runs2:
        mid = (n - 1) / 2
        starts2 = [a for a, _ in runs2]
        if (any(b < mid for _, b in runs2) and any(a > mid for a, _ in runs2)
                and max(b - a for a, b in runs2) + 1 <= n // 2 + 1
                and all(x <= y for x, y in zip(starts2, starts2[1:]))):
            c = next(fr[i][runs2[i][1]] for i in range(nf) if runs2[i][1] > runs2[i][0])
            return {"mode": "rain", "colors": [list(c)], "known": True}

    # 3.7) pulse（中心脉冲，ADR-033 修订 3）：每帧为一段含中点的对称连续 run，
    #      半径先增后减，且存在不触两端的居中帧。
    if () not in runs2 and None not in runs2:
        mid = (n - 1) / 2
        if (all(a <= mid <= b for a, b in runs2)
                and all(a == n - 1 - b for a, b in runs2)
                and any(a > 0 and b < n - 1 for a, b in runs2)
                and len(set(b - a for a, b in runs2)) >= 3):
            c = max((fr[i][b] for i, (a, b) in enumerate(runs2)), key=max)
            return {"mode": "pulse", "colors": [list(c)], "known": True}

    # 3.8) chase（双色追及，ADR-033 修订 3）：全帧全亮、全表恰两色、且并非每帧
    #      同色（同色帧≠渐变的全帧同色系）——gradient/flow/aurora 色数更多不会误入。
    if all(len(set(f)) == 1 or len(set(f)) == 2 for f in fr) and \
            all(all(max(c) > 0 for c in f) for f in fr):
        palette = []
        for f in fr:
            for c in f:
                if not any(_close_rgb(c, d, 10) for d in palette):
                    palette.append(c)
        uniform_all = all(len(set(f)) == 1 for f in fr)
        if len(palette) == 2 and not uniform_all and all(
                len(set(f)) == 2 or _close_rgb(f[0], palette[0], 10) or
                _close_rgb(f[0], palette[1], 10) for f in fr):
            return {"mode": "chase", "colors": [list(palette[0]), list(palette[1])], "known": True}

    # 3.9) fire（火苗，ADR-033 修订 3）：确定性伪噪声——按帧数=16 重建期望亮度
    #      比例矩阵，逐点比对（提取峰值色后全表应在容差内吻合）。
    if nf == 16:
        vmax = [0, 0, 0]
        for f in fr:
            for c in f:
                for ch in range(3):
                    vmax[ch] = max(vmax[ch], c[ch])
        smax = max(0.3 + 0.7 * ((math.sin(2.399 * i + 2 * math.pi * k / 16) *
                                 math.sin(1.7 * i + 2.4 + 2 * math.pi * 3 * k / 16) + 1) / 2)
                   for k in range(16) for i in range(n))
        if max(vmax) > 40:
            ok = True
            for k in range(16):
                for i in range(n):
                    h = (math.sin(2.399 * i + 2 * math.pi * k / 16) *
                         math.sin(1.7 * i + 2.4 + 2 * math.pi * 3 * k / 16) + 1) / 2
                    exp_s = 0.3 + 0.7 * h
                    if any(abs(fr[k][i][ch] / vmax[ch] - exp_s / smax) > 0.06
                           for ch in range(3) if vmax[ch] >= 20):
                        ok = False
                        break
                if not ok:
                    break
            if ok:
                c = [round(v / smax) for v in vmax]
                return {"mode": "fire", "colors": [c], "known": True}

    # 4) rainbow：每帧色相 ≈ (i/n)·360 + 相位（全色环匀速分布、明度固定不接近全黑）
    def rainbow_fit(f):
        hues = [_hue_of(c) for c in f]
        if any(h is None for h in hues):
            return False
        mx = max(max(c) for c in f)
        mn = min(min(c) for c in f)
        if mx == 0 or mn / mx > 0.45:
            return False
        phase = hues[0]
        errs = [min(abs((h - i / n * 360 - phase + 180) % 360 - 180), 180)
                for i, h in enumerate(hues)]
        return sum(errs) / len(errs) < 25

    if all(rainbow_fit(f) for f in fr):
        return {"mode": "rainbow", "colors": [], "known": True}

    # 5) flow：所有帧都是同一基础图案的循环平移（平移量粗扫+爬山细化，不依赖网格对齐）
    def ring_sample(f, x):
        """把灯环当连续函数采样（x 可为小数灯位，环形线性插值）。"""
        i0 = int(math.floor(x)) % n
        t = x - math.floor(x)
        c0, c1 = f[i0], f[(i0 + 1) % n]
        return [c0[k] + (c1[k] - c0[k]) * t for k in range(3)]

    def _shift_err(f0, target, k):
        """target[i] ≈ ring_sample(f0, i+s)·k 的最优平移总误差（粗扫取最优后细化）。"""
        tgt = [[v * k for v in c] for c in target]
        err = lambda s: sum(abs(ring_sample(f0, i + s)[ch] - tgt[i][ch])
                            for i in range(n) for ch in range(3))
        e0, s0 = min((err(q / 4), q / 4) for q in range(n * 4))
        step = 0.05                                     # 爬山细化到 0.01 灯位
        while step >= 0.01:
            moved = True
            while moved:
                moved = False
                for ds in (-step, step):
                    e = err(s0 + ds)
                    if e < e0:
                        e0, s0, moved = e, s0 + ds, True
                        break
            step /= 5
        return e0

    thr = n * 3 * 12                                    # 平均每通道容差 12

    def palette_of(frame, tol=30, cap=5):
        pal = []
        for c in frame:
            if not any(_close_rgb(list(c), list(p), tol) for p in pal):
                pal.append(list(c))
            if len(pal) >= cap:
                break
        return pal

    if all(_shift_err(fr[0], f, 1.0) < thr for f in fr[1:]):
        bright = max(fr, key=lambda f: max(max(c) for c in f))
        pal = palette_of(bright)
        if len(pal) == 1:
            return {"mode": "on", "colors": pal, "known": True}   # 单色"流动"=常亮
        return {"mode": "flow", "colors": pal, "known": True}

    # 6) aurora：图案在流动 + 逐帧全局明暗缩放（=流光×glow）。
    #    以最亮帧为锚，其余帧按亮度归一后能平移对上 → 极光；不满足则老实报未知。
    lit = [f for f in fr if max(max(c) for c in f) > 15]
    if len(lit) >= 2:
        bright = max(lit, key=lambda f: max(max(c) for c in f))
        m0 = max(max(c) for c in bright)
        ok = True
        for f in lit:
            m1 = max(max(c) for c in f)
            if m1 == 0 or _shift_err(bright, f, m0 / m1) >= thr:
                ok = False
                break
        if ok:
            return {"mode": "aurora", "colors": palette_of(bright), "known": True}
    return unknown

