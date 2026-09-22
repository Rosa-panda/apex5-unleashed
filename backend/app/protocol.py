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
    """扫描：逐珠点亮到全亮再逐珠熄灭（2×rgb_num 帧）。"""
    c = tuple(colors[0])
    fill = []
    for k in range(rgb_num):
        frame = bytearray()
        for i in range(rgb_num):
            frame.extend(c if i <= k else (0, 0, 0))
        fill.append(bytes(frame))
    return bytes(b"".join(fill + fill[::-1]))


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
    mode ∈ off/on/breath/gradient/flow/blink/heartbeat/wipe/rainbow/aurora/unknown。
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

    if all(is_prefix(f) for f in fr) and len(set(lit)) >= 3:
        c = next(fr[i][0] for i, k in enumerate(lit) if k > 0)
        return {"mode": "wipe", "colors": [list(c)], "known": True}

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

