# -*- coding: utf-8 -*-
"""屏幕图像格式与打包（ADR-018 R4 二期）。

帧格式来自 openflydigi（MIT, https://github.com/tycrek/openflydigi 由社区作者
Mikalai Kaliaha 发布）并在离线用官方出厂 bin 验证（见 test_screen_offline.py）：

    每帧 25604B = 4B LVGL v8 图像头 + 160x80 RGB565（高字节在前，LV_COLOR_16_SWAP）
    头 = uint32 LE: cf(5bit) | 0(3bit) | 0(2bit) | width(11bit) | height(11bit)
    Apex5 = cf=4(TRUE_COLOR), 160, 80 → 常量 04 80 02 0a

官方容器：帧首尾拼接，无额外包头（screen.split_frames 同款规则）。
打包上限：255 帧（帧数在协议里是 1 字节）；1 帧约 25s、14 帧约 6 min（真机实测），
UI 需把预计耗时展示给用户。
"""
from __future__ import annotations

WIDTH = 160
HEIGHT = 80
HEADER_LEN = 4
PIXEL_BYTES = 2
FRAME_LEN = HEADER_LEN + WIDTH * HEIGHT * PIXEL_BYTES     # 25604
MAX_FRAMES = 255

CF_TRUE_COLOR = 4

# ADR-018 早先记的 "4|160<<10|80<<21" 即此式（同一常量 0x0A028004）
FRAME_HEADER = (CF_TRUE_COLOR & 0x1F) | ((WIDTH & 0x7FF) << 10) | ((HEIGHT & 0x7FF) << 21)


class ScreenPackError(Exception):
    pass


def frame_header(width=WIDTH, height=HEIGHT, cf=CF_TRUE_COLOR) -> bytes:
    return ((cf & 0x1F) | ((width & 0x7FF) << 10) | ((height & 0x7FF) << 21)).to_bytes(4, "little")


def parse_frame_header(data: bytes):
    """(cf, width, height)。LVGL 规定为 0 的位非 0 → 不是本格式，立即报错。"""
    if len(data) < HEADER_LEN:
        raise ScreenPackError("帧长度不足 4 字节头")
    value = int.from_bytes(data[:HEADER_LEN], "little")
    if (value >> 5) & 0x1F:
        raise ScreenPackError(f"非 LVGL 图像头: {data[:HEADER_LEN].hex()}")
    return value & 0x1F, (value >> 10) & 0x7FF, (value >> 21) & 0x7FF


def pack_pixel(red: int, green: int, blue: int):
    """RGB888 → RGB565，高字节在前（byte-swap 布局）。"""
    value = ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)
    return value >> 8, value & 0xFF


def unpack_pixel(high: int, low: int):
    """RGB565 → RGB888，高位复制进低位（往返不色偏）。"""
    value = (high << 8) | low
    r, g, b = (value >> 11) & 0x1F, (value >> 5) & 0x3F, value & 0x1F
    return (r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)


def encode_frame(rgb: bytes, width=WIDTH, height=HEIGHT) -> bytes:
    expected = width * height * 3
    if len(rgb) != expected:
        raise ScreenPackError(f"需要 {expected}B RGB，收到 {len(rgb)}B")
    frame = bytearray(frame_header(width, height))
    out = bytearray(width * height * PIXEL_BYTES)
    for i in range(width * height):
        hi, lo = pack_pixel(rgb[i * 3], rgb[i * 3 + 1], rgb[i * 3 + 2])
        out[i * 2], out[i * 2 + 1] = hi, lo
    frame += out
    return bytes(frame)


def decode_frame(frame: bytes):
    _cf, width, height = parse_frame_header(frame)
    pixels = width * height
    body = frame[HEADER_LEN:HEADER_LEN + pixels * PIXEL_BYTES]
    if len(body) < pixels * PIXEL_BYTES:
        raise ScreenPackError("像素数据不足")
    rgb = bytearray(pixels * 3)
    for i in range(pixels):
        r, g, b = unpack_pixel(body[i * 2], body[i * 2 + 1])
        rgb[i * 3:i * 3 + 3] = r, g, b
    return width, height, bytes(rgb)


def split_frames(data: bytes, frame_len=FRAME_LEN):
    """官方容器 = 帧裸拼接。字节数不是帧整数倍 → 文件不对。"""
    if not data or len(data) % frame_len:
        raise ScreenPackError(f"{len(data)}B 不是 {frame_len}B 帧的整数倍")
    return [bytes(data[i:i + frame_len]) for i in range(0, len(data), frame_len)]


def join_frames(frames) -> bytes:
    return b"".join(frames)


# -- 图像源 → 帧（Pillow 可用时启用） ---------------------------------------

def fit_rgb(img, mode="fill", background=(0, 0, 0)) -> bytes:
    """PIL.Image → 160x80 RGB888 bytes。fill=裁切铺满 / fit=留黑边 / stretch=拉伸。"""
    from PIL import Image
    if mode not in ("fill", "fit", "stretch"):
        raise ScreenPackError(f"未知适配模式 {mode!r}")
    im = img.convert("RGB")
    if mode == "fill":
        scale = max(WIDTH / im.width, HEIGHT / im.height)
        new_w, new_h = round(im.width * scale), round(im.height * scale)
        resized = im.resize((new_w, new_h), Image.BOX)
        left, top = (new_w - WIDTH) // 2, (new_h - HEIGHT) // 2
        canvas = Image.new("RGB", (WIDTH, HEIGHT), background)
        canvas.paste(resized.crop((left, top, left + WIDTH, top + HEIGHT)), (0, 0))
        return canvas.tobytes()
    if mode == "fit":
        scale = min(WIDTH / im.width, HEIGHT / im.height)
        new_w, new_h = max(1, round(im.width * scale)), max(1, round(im.height * scale))
        canvas = Image.new("RGB", (WIDTH, HEIGHT), background)
        resized = im.resize((new_w, new_h), Image.BOX)
        canvas.paste(resized, ((WIDTH - new_w) // 2, (HEIGHT - new_h) // 2))
        return canvas.tobytes()
    return im.resize((WIDTH, HEIGHT), Image.BOX).tobytes()


def frames_from_gif(path: str, mode="fill", max_frames=MAX_FRAMES, target=None):
    """GIF → ([RGB 帧], interval_ms, 是否截断)。

    target=抽帧目标数：全片**等距**取 target 帧，帧间隔按步长放大——保持原速观感
    （50fps 抽 1/5 → 10fps 100ms）。烧写耗时 ∝ 帧数（约 24.7s/帧），高帧率 GIF
    在 160×80 屏上纯属浪费，不抽帧就是拿 60 分钟换肉眼不可见的流畅。
    未超上限时不截断。
    """
    from PIL import Image, ImageSequence
    im = Image.open(path)
    total = getattr(im, "n_frames", 1)
    stride = 1
    if target and total > target:
        stride = max(1, round(total / target))
    picked = list(range(0, total, stride))
    if len(picked) > max_frames:                  # 抽完仍超硬上限才截断
        picked = picked[:max_frames]
    durations = []
    rgb_frames = []
    for i, frame in enumerate(ImageSequence.Iterator(im)):
        if i not in picked:
            continue
        durations.append(frame.info.get("duration", 100) or 100)
        rgb_frames.append(fit_rgb(frame.copy(), mode))
    if not rgb_frames:
        raise ScreenPackError("GIF 中没有可用帧")
    durations.sort()
    interval = durations[len(durations) // 2] * stride
    truncated = len(picked) >= max_frames and total > len(picked)
    return rgb_frames, interval, truncated


def frames_from_image(path_or_img, mode="fill"):
    from PIL import Image
    im = path_or_img if hasattr(path_or_img, "convert") else Image.open(path_or_img)
    return [fit_rgb(im, mode)]


def pack_bin(frames, interval_ms=100) -> bytes:
    """帧列表 → 可烧写 bin（帧拼接，无容器头）。"""
    if not frames:
        raise ScreenPackError("没有帧")
    if len(frames) > MAX_FRAMES:
        raise ScreenPackError(f"{len(frames)} 帧超出 {MAX_FRAMES} 上限（协议帧数 1 字节）")
    for i, f in enumerate(frames):
        if isinstance(f, bytes):
            if len(f) != FRAME_LEN:
                raise ScreenPackError(f"帧 {i} 长度 {len(f)} != {FRAME_LEN}")
        else:  # RGB888 bytes
            if len(f) != WIDTH * HEIGHT * 3:
                raise ScreenPackError(f"帧 {i} RGB 长度不符")
    return join_frames(f if isinstance(f, bytes) else encode_frame(f) for f in frames)


def frame_rate(interval_ms: float) -> int:
    """官方 frameRate = round(interval/10)，百分之一秒。与 HID 路径的 /100 不同——
    本项目只走串口路径，用这个。"""
    return max(1, min(255, int(round(interval_ms / 10.0))))


def estimate_seconds(frame_count: int) -> int:
    """预计烧写耗时。真机实测（Apex5，2026-09-19）：30 帧 ≈ 90s → 约 3s/帧
    （in_waiting 事件驱动读后实际 ~167 包/s，远快于 openflydigi 的 19 包/s）。"""
    return int(round(frame_count * 3.0))
