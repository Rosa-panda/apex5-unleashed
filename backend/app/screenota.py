# -*- coding: utf-8 -*-
"""屏幕图片上传——串口 OTA 路径（k5/Apex5 唯一能点亮面板的通道）。

移植自 openflydigi `flydigi/screen_ota.py`（MIT, © 2026 Mikalai Kaliaha），
真机验证记录：有线 Apex5，测试卡 + 14 帧动画均成功写入 base 0x002ff000 并自动重启
（openflydigi PROTOCOL.md §8d）。Windows 侧差异仅两处：端口发现走
serial.tools.list_ports（替代 Linux sysfs），串口用 pyserial（替代 termios）。

协议（§8d， opcode 为主机→设备方向）：
    出: [opcode][len uint16 LE][payload...]        len 是每-opcode 常量，不可推算
    回: [result][opcode][len uint16 LE][payload...]（<5B 短回复只含 result+opcode）
    11 PicGetBaseAddr(4B) → baseAddr    10 PicGetVersion(无载荷)
     3 EraseSector(addr) × ceil(n/4096) 5 WriteData(addr+55B) × ceil(n/55)
    12 PicResetDevice(totalLen, crc32) → 芯片复位重启

安全边界（写进 ADR-018 的三条，移植时保持不变）：
    ① 图区基址从芯片读回（11），一切擦写 = base+offset，CUSTOM_PIC 永不触及程序区；
    ② 12 是协议定义的退出；③ 出厂动画随官方空间站自带，烧坏有官方恢复路径
    （isRestoreDefault=1 + default_screen_image bin）。
"""
from __future__ import annotations

import struct
import time

import screenpack   # 与 app/ 内其它模块同款平铺导入（engine.py 同风格）

CMD_SWITCH_USB = 31
CHIP_SCREEN = 4

OP_ERASE = 3
OP_WRITE = 5
OP_PIC_GET_VERSION = 10
OP_PIC_GET_BASE = 11
OP_PIC_RESET = 12

PIC_TYPE_GIF = 1     # >1 帧
PIC_TYPE_PNG = 2     # 单帧

USB_VID = 0xFFAA
USB_PID = 0x5555
BAUD = 921600

ERASE_BLOCK = 4096
WRITE_CHUNK = 55

REPLY_TIMEOUT = 18.0     # 官方 300ms 定时器 × 60 拍
PORT_TIMEOUT = 30.0
SWITCH_SETTLE = 5.0      # 官方硬编码等待

# 每-opcode 长度常量。三个与实际载荷不一致（见 §8d「不可推算」）——照抄，不计算。
LENGTH_FIELD = {
    OP_PIC_GET_BASE: 4,
    OP_PIC_GET_VERSION: 6,
    OP_ERASE: 6,
    OP_WRITE: 64,
    OP_PIC_RESET: 8,
}


class OtaError(Exception):
    pass


# -- 校验和（官方 AppOtasCrcCal 的 C# 语义复刻） ------------------------------

_POLY_TABLE = None


def _table():
    global _POLY_TABLE
    if _POLY_TABLE is None:
        table = []
        for index in range(256):
            value = index
            for _ in range(8):
                value = (value >> 1) ^ (0xEDB88320 if value & 1 else 0)
            table.append(value)
        _POLY_TABLE = table
    return _POLY_TABLE


def _to_signed(value):
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


def checksum(data: bytes) -> int:
    """C# int 语义：`crc / 256` 是向零截断的有符号除法，不是 >> 8。"""
    table = _table()
    crc = 0
    for byte in data:
        quotient = int(crc / 256)
        crc = _to_signed(crc << 8)
        crc = _to_signed(crc ^ _to_signed(table[(quotient ^ byte) & 0xFF]))
    return crc & 0xFFFFFFFF


# -- 端口（Windows：pyserial 枚举 VID/PID） ------------------------------------

def find_port(vid=USB_VID, pid=USB_PID):
    from serial.tools import list_ports
    for p in list_ports.comports():
        if p.vid == vid and p.pid == pid:
            return p.device
    return None


def wait_for_port(timeout=PORT_TIMEOUT, poll=0.5, vid=USB_VID, pid=USB_PID):
    deadline = time.monotonic() + timeout
    while True:
        port = find_port(vid, pid)
        if port:
            return port
        if time.monotonic() >= deadline:
            raise OtaError(
                f"{timeout:g}s 内未出现 {vid:04x}:{pid:04x} 串口。手柄可能没切进升级模式——"
                "拨背面电源开关重启手柄，确认能被识别为手柄后再试。")
        time.sleep(poll)


# -- 串口链路（pyserial，921600 8N1，DTR/RTS 拉高） -----------------------------

class OtaLink:
    def __init__(self, path):
        import serial
        self.path = path
        self.ser = serial.Serial()
        self.ser.port = path
        self.ser.baudrate = BAUD
        self.ser.bytesize = serial.EIGHTBITS
        self.ser.parity = serial.PARITY_NONE
        self.ser.stopbits = serial.STOPBITS_ONE
        self.ser.xonxoff = False
        self.ser.rtscts = False
        self.ser.dsrdtr = False
        self.ser.timeout = 0.2
        self.ser.write_timeout = 5.0
        self.ser.open()
        self.ser.dtr = True      # 官方 SerialPort DtrEnable/RtsEnable
        self.ser.rts = True
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

    def close(self):
        if self.ser is not None:
            self.ser.close()
            self.ser = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def write(self, data):
        self.ser.write(data)

    def read_reply(self, timeout=REPLY_TIMEOUT):
        """一条回复。事件驱动：数据一到立刻返回（pyserial 的 read(64) 会等满
        64 字节或整个超时——回复只有 8B，等超时就是每次交换白丢 200ms）。"""
        import time as _t
        deadline = _t.monotonic() + timeout
        buf = b""
        while _t.monotonic() < deadline:
            n = self.ser.in_waiting
            if not n:
                _t.sleep(0.001)
                continue
            buf += self.ser.read(n)
            # 分片回复收尾窗：静默 3ms 视为完整
            while True:
                _t.sleep(0.003)
                n = self.ser.in_waiting
                if not n:
                    return buf
                buf += self.ser.read(n)
        return buf or None


# -- 状态机 -------------------------------------------------------------------

def build(opcode, payload=b""):
    return bytes([opcode]) + struct.pack("<H", LENGTH_FIELD[opcode]) + payload


def parse(reply):
    """(result, opcode, payload)。"""
    if reply is None or len(reply) < 2:
        return None, None, b""
    if len(reply) < 5:
        return reply[0], reply[1], b""
    return reply[0], reply[1], reply[4:]


def picture_type(frame_count):
    return PIC_TYPE_PNG if frame_count == 1 else PIC_TYPE_GIF


def upload(link, frames, interval_ms=100, restore_default=False, progress=None):
    """向已打开的链路写入整组图片。返回使用的图区基址。"""
    data = screenpack.join_frames(frames)
    if not data:
        raise OtaError("没有数据可写")
    if len(frames) > screenpack.MAX_FRAMES:
        raise OtaError(f"{len(frames)} 帧超上限 {screenpack.MAX_FRAMES}")

    def exchange(opcode, payload=b"", expect=None):
        link.write(build(opcode, payload))
        result, got, body = parse(link.read_reply())
        if got is None:
            raise OtaError(f"opcode {opcode} 无回复")
        if expect is not None and got != expect:
            raise OtaError(f"opcode {opcode}: 期望回复 {expect}，收到 {got}（result={result}）")
        # 注意：不检查 result 字节——openflydigi 原版同款（成功值未必是 1，
        # 首烧误报「传输失败」即此处的多余检查所致，已移除）
        return result, body

    _result, body = exchange(OP_PIC_GET_BASE, bytes([
        picture_type(len(frames)),
        len(frames) & 0xFF,
        screenpack.frame_rate(interval_ms),
        1 if restore_default else 0,
    ]), expect=OP_PIC_GET_BASE)
    if len(body) < 4:
        raise OtaError("设备未返回图区基址")
    base = struct.unpack("<I", body[:4])[0]

    exchange(OP_PIC_GET_VERSION, expect=OP_PIC_GET_VERSION)

    erases = (len(data) + ERASE_BLOCK - 1) // ERASE_BLOCK
    writes = (len(data) + WRITE_CHUNK - 1) // WRITE_CHUNK
    total = erases + writes
    done = 0

    for index in range(erases):
        exchange(OP_ERASE, struct.pack("<I", base + index * ERASE_BLOCK), expect=OP_ERASE)
        done += 1
        if progress:
            progress(done, total, "erase")

    for index in range(writes):
        offset = index * WRITE_CHUNK
        chunk = data[offset:offset + WRITE_CHUNK]
        # 尾包内长仍写 55、整包自然变短——官方与 openflydigi 同款
        exchange(OP_WRITE,
                 struct.pack("<I", base + offset) + struct.pack("<H", WRITE_CHUNK) + chunk,
                 expect=OP_WRITE)
        done += 1
        if progress:
            progress(done, total, "write")

    link.write(build(OP_PIC_RESET,
                     struct.pack("<I", len(data)) + struct.pack("<I", checksum(data))))
    _result, got, _body = parse(link.read_reply())
    if got != OP_PIC_RESET:
        raise OtaError(f"设备未确认复位（收到 {got}）")
    return base


def switch_to_screen_upgrade(send_frame, wait=0.5):
    """HID cmd 31（chipModule=SCREEN=4）。send_frame 由 engine 提供。

    回执不作判定依据：实测该命令可能无 ACK 而 tty 照样出现，决定性检查是串口。
    """
    try:
        send_frame(CMD_SWITCH_USB, bytes([CHIP_SCREEN]))
    except OSError:
        pass


def upload_picture(send_frame, frames, interval_ms=100, restore_default=False,
                   progress=None, settle=SWITCH_SETTLE, port=None,
                   on_stage=None):
    """全流程：切模式 → 等串口 → 写入 → 芯片自重启（约 15s 同步）。

    send_frame(cmd, payload)：engine 侧 HID 发送器（cmd 31 用）。
    port 传入时跳过切换（用于失败重试时芯片已在升级模式）。
    on_stage(stage)：阶段回调 'switch'/'port'/'flash'/'reboot'。
    """
    if on_stage:
        on_stage("switch")
    if port is None:
        switch_to_screen_upgrade(send_frame)
        time.sleep(settle)
        if on_stage:
            on_stage("port")
        port = wait_for_port()
    if on_stage:
        on_stage("flash")
    with OtaLink(port) as link:
        base = upload(link, frames, interval_ms, restore_default, progress)
    if on_stage:
        on_stage("reboot")
    return base
