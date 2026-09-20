# DSX UDP ingress（ADR-025）：监听 127.0.0.1:7878，消费 DualSenseX 协议事件流。
#
# 逆向实锤（2026-09-20，docs/adr/ADR-025-official-mod-impersonation.md）：
# - 飞智官方 Mod（AdapterTrigger_*.exe）往 127.0.0.1:7878/UDP 发 DSX 协议 JSON：
#     {"instructions": [{"type": 1, "parameters": [手柄号, 侧, 19, 模式, p1..p5]}]}
#   侧：1=左 2=右；第 3 位 19 = 飞智扩展 magic；模式/参数即 cmd51 wire 字节成品
#   （官方服务 ForceTriggerConfigCommon 原样转发，零翻译）。
# - DSX 社区 mod 生态同端口同格式，第 3 位为 DSX TriggerMode 0-18（无 19）。
# - 端口占用时官方 fallback 到 8787，我们同样处理。
# - DSX 客户端按 C:\Temp\DualSenseX\DualSenseX_PortNumber.txt 发现端口——写入做兼容。
#
# 防洪坝（ADR-009）：收包端排空（内核丢旧），去重（与上一包完全相同不重发），
# 每侧最小间隔 15ms 限频；真瓶颈是 32B 中断端点，坝建在 HID 写出前。
import json
import os
import socket
import threading
import time

import protocol

DSX_PORT_FILE = os.path.join(os.environ.get("TEMP") or r"C:\Temp",
                             "DualSenseX", "DualSenseX_PortNumber.txt")

# 官方 wire 模式（AdapterTriggerType + SetForceTriggerCommandFactory 反编译）：
# 0 Normal / 1 Race / 2 (Sniper 布局) / 3 (Recoil 布局) / 4 Lock / 5 Vibration。
# ⚠ 我们的 TRIGGER_MODES 序：normal race recoil sniper lock vibration —— wire2/3
# 的手感命名与官方字面相反（ADR-022 勘误），但字段布局按 wire 一一对齐，直通无碍。
WIRE_MODE_NAMES = {0: "normal", 1: "race", 2: "recoil", 3: "sniper", 4: "lock", 5: "vibration"}
WIRE_MODE_FIELDS = {   # wire id → 字段名列表（与 protocol.TRIGGER_MODES 布局同源，账本展示用）
    0: [],
    1: ["stroke", "resistance", "match"],
    2: ["stroke", "press", "strength", "freq", "match"],
    3: ["stroke", "recoil_stroke", "strength", "match"],
    4: ["stroke", "strength", "match"],
    5: ["stroke", "press", "strength", "freq", "match"],
}

FLYDIGI_MAGIC = 19          # parameters[2] == 19 → 后续是飞智 wire 成品字节
INSTRUCTION_TRIGGER = 1     # DSX InstructionType：1 = TriggerUpdate（我们只消费这个）

# DSX 标准模式（社区 mod）→ 我们的近似翻译（体验级，够用；不认识的忽略并计数）
# DSX Resistance: start 0-9 / force 0-8 → race（油门阻尼手感）
DSX_RIGID_LEVELS = {   # DSX 固定阻尼档 → race resistance 档（比例放大）
    "VerySoft": 40, "Soft": 70, "Medium": 110, "Hard": 150,
    "VeryHard": 190, "Hardest": 230, "Rigid": 255, "GameCube": 160,
}

MIN_INTERVAL = 0.015        # 每侧 HID 写出最小间隔（15ms ≈ 66Hz，够 F1 遥测满频）


def _b(v, default=0):
    try:
        return int(v) & 0xFF
    except (TypeError, ValueError):
        return default


class DsxIngress:
    """7878 收包 → cmd51。engine_getter 延迟取引擎（设备可能后上线）。"""

    def __init__(self, engine_getter, enabled=True):
        self._engine_getter = engine_getter
        self.enabled = enabled
        self.port = None                       # 实际绑定端口（None=没起来）
        self.error = ""                        # 起不来的原因（7878/8787 都被占）
        self.packets = 0                       # 收包计数（诊断/状态页）
        self.applied = 0                       # 实际写到手柄的条数
        self.ignored = 0                       # 不认识的指令计数
        self.last_packet_at = None
        self._sock = None
        self._stop = threading.Event()
        self._last_payload = {}                # side → 上次发出的 payload bytes（去重）
        self._last_send = {}                   # side → 上次写出时刻（限频）
        self.on_applied = None                 # 游戏事件钩子（灯效桥联动，service 接线）
        self._thread = None

    # ---------- 生命周期 ----------
    def start(self):
        if not self.enabled:
            self.error = "未启用"
            return False
        for port in (7878, 8787):              # 官方 fallback 顺序
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", port))
                self._sock = s
                self.port = port
                break
            except OSError as e:
                self.error = f"7878/8787 均被占用（{e}）——若飞智空间站服务在跑请停用"
        if not self._sock:
            return False
        self._write_port_file()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="dsx-ingress")
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        self._sock = None
        self.port = None

    def _write_port_file(self):
        """DSX 生态端口发现文件（官方客户端也写这个；DSX 社区 mod 读它找端口）。"""
        try:
            os.makedirs(os.path.dirname(DSX_PORT_FILE), exist_ok=True)
            with open(DSX_PORT_FILE, "w") as f:
                f.write(str(self.port))
        except Exception:
            pass

    def _loop(self):
        while not self._stop.is_set():
            try:
                data, _addr = self._sock.recvfrom(65535)
            except OSError:
                if self._stop.is_set():
                    return
                continue                      # 瞬时网络栈错误：继续收
            self.packets += 1
            self.last_packet_at = time.strftime("%H:%M:%S")
            try:
                pkt = json.loads(data.decode("ascii", errors="ignore"))
            except Exception:
                continue
            ins = pkt.get("instructions")
            if not isinstance(ins, list):
                continue
            for ins_i in ins:
                if not isinstance(ins_i, dict) or ins_i.get("type") != INSTRUCTION_TRIGGER:
                    self.ignored += 1
                    continue
                params = ins_i.get("parameters")
                if isinstance(params, list) and len(params) >= 3:
                    self._handle_trigger(params)

    # ---------- 翻译 ----------
    def _handle_trigger(self, params):
        side = _b(params[1])                    # 1=左 2=右（DSX Trigger 枚举）
        if side not in (1, 2):
            return
        magic_or_mode = _b(params[2])
        if magic_or_mode == FLYDIGI_MAGIC and len(params) >= 4:
            # 飞智 mod：parameters[3]=wire 模式，[4..9]=成品参数字节 → 直通
            # （补零到定长 5：cmd51 各 wire 模式参数区定长，mod 短包按官方语义补 0）
            wire_mode = _b(params[3])
            vals = [_b(p) for p in params[4:9]]
            body = bytes([wire_mode] + vals + [0] * (5 - len(vals)))
        else:
            body = self._translate_dsx(magic_or_mode, params[3:])
            if body is None:
                self.ignored += 1
                return
            wire_mode = body[0]
        payload = bytes([1, side]) + body       # [apply=1, side, mode, params...]（cmd51 payload）
        self._send(side, payload, wire_mode)

    def _translate_dsx(self, dsx_mode, rest):
        """DSX 标准 TriggerMode(0-18) → 我们的 wire 字节（近似手感，社区 mod 兜底）。
        返回 bytes([mode, params...]) 或 None（不认识）。"""
        r = [_b(v) for v in rest]
        if dsx_mode == 0:                       # Normal
            return bytes([0])
        if dsx_mode == 13 and len(r) >= 2:      # Resistance(start 0-9, force 0-8) → race
            return bytes([1, round(r[0] / 9 * 255), max(1, round(r[1] / 8 * 255)), 1])
        if dsx_mode == 14 and len(r) >= 3:      # Bow(start,end,force,..) → race 弓感近似
            return bytes([1, round(r[0] / 8 * 255), max(1, round(r[2] / 8 * 255)), 1])
        if dsx_mode == 8 and len(r) >= 1:       # VibrateTrigger(intensity) → vibration
            return bytes([5, 10, max(1, r[0]), r[0], 40, 1])
        if dsx_mode == 11:                      # VibrateTriggerPulse → vibration 脉动感
            return bytes([5, 10, 30, 80, 30, 1])
        for name, lvl in DSX_RIGID_LEVELS.items():   # 固定阻尼档
            if dsx_mode == {"VerySoft": 2, "Soft": 3, "Hard": 4, "VeryHard": 5,
                            "Hardest": 6, "Rigid": 7, "GameCube": 1, "Medium": 10,
                            "Choppy": 9}.get(name):
                return bytes([1, 0, lvl, 1])
        return None                              # CustomTriggerValue/Gun 系：布局差异大，不硬译

    # ---------- 写出（去重 + 限频，ADR-009 防洪坝） ----------
    def _send(self, side, payload, wire_mode):
        if payload == self._last_payload.get(side):
            return
        t = time.monotonic()
        if t - self._last_send.get(side, 0.0) < MIN_INTERVAL:
            return                              # 限频窗内直接丢（下一包更真）
        eng = self._engine_getter()
        if not eng or not eng.online or eng.proxy.get("holder") != "self":
            return                              # 手柄不在/代理权不在手：只收不发
        self._last_payload[side] = payload
        self._last_send[side] = t
        frame = protocol.build(protocol.CMD_TRIGGER, payload)
        eng._send(frame, f"dsx:{WIRE_MODE_NAMES.get(wire_mode, wire_mode)}")
        # 账本（UI 可见当前事件级状态）
        sname = "left" if side == 1 else "right"
        fields = WIRE_MODE_FIELDS.get(wire_mode, [])
        eng.state["triggers"][sname] = {
            "mode": WIRE_MODE_NAMES.get(wire_mode, f"wire{wire_mode}"),
            "params": {f: v for f, v in zip(fields, list(payload[2:]))},
            "source": "dsx:mod", "applied_at": time.strftime("%H:%M:%S")}
        self.applied += 1
        if self.on_applied:
            try:
                self.on_applied(sname, wire_mode)
            except Exception:
                pass

    def clear_ledger(self):
        """mod 停止/游戏退出时清去重缓存（下次进场立刻生效）。"""
        self._last_payload.clear()

    def status(self):
        return {"enabled": self.enabled, "port": self.port, "error": self.error,
                "packets": self.packets, "applied": self.applied, "ignored": self.ignored,
                "last_packet_at": self.last_packet_at}
