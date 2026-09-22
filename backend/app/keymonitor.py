# 特殊键监听（宏的前置）：键盘接口解码 + vendor 非协议帧透传
# 八5 的背键/肩部扩展键不在标准 XInput 里，走 MI_01 键盘集合或 vendor 接口，
# 这里两条都听，先让键"可见"，确认编码后再做命名映射与宏。
import threading
import time

import protocol

# HID Usage Table 键盘页（0x04-0x73 常用段）
KEYCODES = {
    0x04: "A", 0x05: "B", 0x06: "C", 0x07: "D", 0x08: "E", 0x09: "F", 0x0A: "G",
    0x0B: "H", 0x0C: "I", 0x0D: "J", 0x0E: "K", 0x0F: "L", 0x10: "M", 0x11: "N",
    0x12: "O", 0x13: "P", 0x14: "Q", 0x15: "R", 0x16: "S", 0x17: "T", 0x18: "U",
    0x19: "V", 0x1A: "W", 0x1B: "X", 0x1C: "Y", 0x1D: "Z", 0x1E: "1", 0x1F: "2",
    0x20: "3", 0x21: "4", 0x22: "5", 0x23: "6", 0x24: "7", 0x25: "8", 0x26: "9",
    0x27: "0", 0x28: "Enter", 0x29: "Esc", 0x2A: "Backspace", 0x2C: "Space",
    0x2D: "-", 0x2E: "=", 0x2F: "[", 0x30: "]", 0x33: ";", 0x34: "'",
    0x36: ",", 0x37: ".", 0x38: "/", 0x39: "CapsLock", 0x4C: "Del",
    0x4F: "Right", 0x50: "Left", 0x51: "Down", 0x52: "Up",
    0x53: "NumLock", 0x54: "Pad/", 0x55: "Pad*", 0x56: "Pad-", 0x57: "Pad+",
    0x58: "PadEnter", 0x59: "Pad1", 0x5A: "Pad2", 0x5B: "Pad3", 0x5C: "Pad4",
    0x5D: "Pad5", 0x5E: "Pad6", 0x5F: "Pad7", 0x60: "Pad8", 0x61: "Pad9",
    0x62: "Pad0", 0x63: "Pad.",
    0x68: "F13", 0x69: "F14", 0x6A: "F15", 0x6B: "F16", 0x6C: "F17",
    0x6D: "F18", 0x6E: "F19", 0x6F: "F20", 0x70: "F21", 0x71: "F22",
    0x72: "F23", 0x73: "F24",
    0xE0: "LCtrl", 0xE1: "LShift", 0xE2: "LAlt", 0xE3: "LWin",
    0xE4: "RCtrl", 0xE5: "RShift", 0xE6: "RAlt", 0xE7: "RWin",
}
MOD_BITS = [(1, "Ctrl"), (2, "Shift"), (4, "Alt"), (8, "Win"),
            (0x10, "RCtrl"), (0x20, "RShift"), (0x40, "RAlt"), (0x80, "RWin")]

# 手柄最近主动输入时刻（monotonic；0=未知）：键盘/游戏盘监听接口收到**内容变化**
# 的报告才刷新。电量心跳（main.monitor_loop）据此在手柄静默挂机时停发——固件把
# 主机 report 当活动，心跳不停手柄永不休眠（2026-09-22 用户实锤，与 0xEF 流同因）。
# ⚠ 不能用「收到包」判：实测游戏盘接口空闲时也 ~5s 周期重发恒定的摇杆居中态帧，
# 收到即刷会让判据永远新鲜、心跳永不停（2026-09-22 静默实验实锤）。内容变化 =
# 摇杆/按键/扳机动 = 用户真的在操作。
last_input = 0.0


def find_keyboard_path():
    try:
        import hid
        for dev in hid.enumerate(protocol.VID, protocol.PID):
            if dev.get("usage_page") == 0x0001 and dev.get("usage") == 0x0006:
                return dev["path"]
    except Exception:
        pass
    return None


class KeyMonitor:
    """键盘接口监听：报告 [id, modifier, rsv, k1..k6]，按键集合变化即上报。"""

    def __init__(self, emit):
        self._emit = emit
        self._stop = threading.Event()
        self._pressed = frozenset()

    def start(self):
        path = find_keyboard_path()
        if not path:
            self._emit("info", detail="未找到键盘接口（手柄可能不在 XInput 键盘映射模式）")
            return False
        try:
            import hid
            dev = hid.device()
            dev.open_path(path)
        except Exception as e:
            self._emit("info", detail=f"键盘接口打开失败: {e}")
            return False
        threading.Thread(target=self._loop, args=(dev,), daemon=True, name="key-monitor").start()
        return True

    def _loop(self, dev):
        global last_input
        while not self._stop.is_set():
            try:
                data = dev.read(64, timeout_ms=50)
            except Exception:
                # 接口异常（映射切换/重枚举会瞬时断）：重开句柄继续，别静默死掉
                import hid
                try:
                    dev.close()
                except Exception:
                    pass
                dev = None
                while not self._stop.is_set() and dev is None:
                    time.sleep(1.0)
                    p = find_keyboard_path()
                    if p:
                        try:
                            dev = hid.device()
                            dev.open_path(p)
                        except Exception:
                            dev = None
                continue
            if not data or len(data) < 8:
                continue
            rep = bytes(data)
            mods = [n for bit, n in MOD_BITS if rep[1] & bit]
            keys = frozenset(KEYCODES.get(b) for b in rep[3:9] if b)
            cur = frozenset(list(keys) + mods)
            if cur != self._pressed:
                last_input = time.monotonic()  # 键位真变化（电量心跳判据，模块级）
                pressed_now = [k for k in cur if k not in self._pressed]
                self._pressed = cur
                self._emit("hidkey", keys=sorted(cur), raw=rep.hex(" "),
                           pressed=pressed_now)

    def stop(self):
        self._stop.set()


# 拓展键事实（2026-09-18 三轮实测+用户指认，ADR-016 最终版）：
#   6 键 = LM/RM（头部）+ M1-M4（背部），默认固件下**全接口零输出**（逐事件抓取确认）。
#   早期 byte10 bit4/5 "发现" = 误碰杂讯，已推翻——勿再引用。
#   可见唯一通路 = cmd 0xA3 映射写入（任务#8，关键路径）。激活后经受控校准归因键位。
SPECIAL_BYTE_BASE = 10           # 按钮填充区起始字节（激活后从这里解码）
BUILTIN_LABELS = {}              # 不硬编码猜测：bit→键名只信校准结果
ATTRIB_KEYS = ["LM", "RM", "M1", "M2", "M3", "M4"]   # 用户实机命名：头部两键 LM/RM（2026-09-18）
ATTRIB_WINDOW = 5.0              # 每键采集窗口秒数


def keymap_path():
    import os
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "Apex5Unleashed")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "keymap.json")


def load_labels():
    labels = dict(BUILTIN_LABELS)
    try:
        import json
        with open(keymap_path(), "r", encoding="utf-8") as f:
            for raw, name in json.load(f).items():
                b, bit = raw.split(".")
                labels[(int(b), int(bit))] = name
    except Exception:
        pass
    return labels


def find_gamepad_path():
    try:
        import hid
        for dev in hid.enumerate(protocol.VID, protocol.PID):
            if dev.get("usage_page") == 0x0001 and dev.get("usage") == 0x0005:
                return dev["path"]
    except Exception:
        pass
    return None


class GamepadRawMonitor:
    """游戏盘接口原始读取：解码描述符外填充字节的拓展键位 + 受控键位校准。"""

    ACTIVE = None                               # 最新实例（service 层触发校准用）

    def __init__(self, emit):
        self._emit = emit
        self._stop = threading.Event()
        self._bits = {}
        self._last_rep = b""                    # 上一次游戏盘报告原文（内容变化=有操作）
        self._labels = load_labels()
        self._attrib_key = None                 # 当前校准窗口的键名（None=不在采集）
        self._attrib_hits = {}                  # (off,bit) -> {键名: 按下次数}
        self._attrib_running = False

    def start(self):
        path = find_gamepad_path()
        if not path:
            self._emit("info", detail="未找到游戏盘接口")
            return False
        try:
            import hid
            dev = hid.device()
            dev.open_path(path)
        except Exception as e:
            self._emit("info", detail=f"游戏盘接口打开失败: {e}")
            return False
        GamepadRawMonitor.ACTIVE = self
        threading.Thread(target=self._loop, args=(dev,), daemon=True, name="padraw-monitor").start()
        return True

    def _loop(self, dev):
        global last_input
        while not self._stop.is_set():
            try:
                data = dev.read(64, timeout_ms=20)
            except Exception:
                # 同键盘监听：断开重连而非静默退出
                try:
                    dev.close()
                except Exception:
                    pass
                dev = None
                import hid
                while not self._stop.is_set() and dev is None:
                    time.sleep(1.0)
                    p = find_gamepad_path()
                    if p:
                        try:
                            dev = hid.device()
                            dev.open_path(p)
                        except Exception:
                            dev = None
                continue
            if not data or len(data) <= SPECIAL_BYTE_BASE:
                continue
            rep = bytes(data)
            if rep != self._last_rep:          # 内容变化才算操作（空闲时 ~5s 周期重发恒定态）
                self._last_rep = rep
                last_input = time.monotonic()  # 手柄主动输入（电量心跳判据，模块级）
            for off in range(SPECIAL_BYTE_BASE, min(len(rep), SPECIAL_BYTE_BASE + 4)):
                for bit in range(8):
                    on = bool(rep[off] & (1 << bit))
                    key = (off, bit)
                    if self._bits.get(key, False) != on:
                        self._bits[key] = on
                        raw = f"b{off}.{bit}"
                        if on:      # 只上报按下/松开变化，不发首次基线
                            if self._attrib_key:     # 校准窗口内：按下事件归因到当前提示键
                                hits = self._attrib_hits.setdefault(key, {})
                                hits[self._attrib_key] = hits.get(self._attrib_key, 0) + 1
                            self._emit("speckey", key=self._labels.get(key, raw), raw=raw, state=1)
                        else:
                            self._emit("speckey", key=self._labels.get(key, raw), raw=raw, state=0)

    # ---- 受控键位校准（ADR-016：bit→物理键唯一可信来源）----
    def start_attribution(self):
        """依次提示用户按 FL→FR→M1..M4，每键独立时间窗，窗口内翻转的 bit 归给该键。"""
        if self._attrib_running:
            return False
        self._attrib_running = True
        threading.Thread(target=self._attrib_run, daemon=True, name="key-attrib").start()
        return True

    def _attrib_run(self):
        import json
        try:
            self._attrib_hits = {}
            for key in ATTRIB_KEYS:
                self._emit("attrib", phase="prompt", key=key, window=ATTRIB_WINDOW)
                time.sleep(1.0)                 # 给用户看清提示
                self._attrib_key = key
                self._emit("attrib", phase="window", key=key)
                time.sleep(ATTRIB_WINDOW)
                self._attrib_key = None
            # 归因：bit 归给按下次数最多的窗口（并列取先出现的键）
            mapping, conflicts = {}, []
            for bit, hits in self._attrib_hits.items():
                best = max(hits.items(), key=lambda kv: (kv[1], -ATTRIB_KEYS.index(kv[0])))
                if len(hits) > 1:
                    conflicts.append(f"b{bit[0]}.{bit[1]}: {hits}")
                mapping[f"b{bit[0]}.{bit[1]}"] = best[0]
            if mapping:
                with open(keymap_path(), "w", encoding="utf-8") as f:
                    json.dump(mapping, f, ensure_ascii=False, indent=2)
                self._labels = load_labels()
            missing = [k for k in ATTRIB_KEYS if k not in mapping.values()]
            self._emit("attrib", phase="done", mapping=mapping, missing=missing,
                       conflicts=conflicts,
                       note="missing 中的键在该接口无任何输出" +
                            ("（M 系列静默 = 需 0xA3 映射写入，ADR-016）" if any(m.startswith("M") for m in missing) else ""))
        except Exception as e:
            self._emit("attrib", phase="error", detail=str(e))
        finally:
            self._attrib_running = False

    def stop(self):
        self._stop.set()
