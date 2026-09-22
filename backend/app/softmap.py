# 软件层体感瞄准 + 摇杆→鼠键（ADR-027，体验区）。
# 数据源：引擎 0xEF 帧运动分发（engine.subscribe_motion）；输出：Windows SendInput。
# 算法骨架照抄官方 KeyboardMouseInjectRunner 反编译：GyroScale=1000/16384（raw→deg/s）、
# 死区 |raw|<8、加速曲线阈值 2 指数 1.3、灵敏度/50。
# 像素增益常数反编译里对不上（官方按自己注入器标定）——暴露为 gain，UI 注明「手感待真机调」。
import ctypes
import json
import os
import threading
import time
from ctypes import wintypes

GYRO_SCALE = 1000.0 / 16384.0     # 0.06103702，raw → deg/s
GYRO_DEADZONE_RAW = 8
CURVE_THRESHOLD = 2.0
CURVE_EXP = 1.3
STICK_MAX = 16384

# ---- SendInput ----
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32")

_INPUT_MOUSE, _INPUT_KEYBOARD = 0, 1
_MOUSEEVENTF_MOVE = 0x0001
_KEYEVENTF_KEYUP, _KEYEVENTF_SCANCODE = 0x0002, 0x0008


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def mouse_move(dx, dy):
    inp = _INPUT(type=_INPUT_MOUSE)
    inp.mi = _MOUSEINPUT(int(dx), int(dy), 0, _MOUSEEVENTF_MOVE, 0, None)
    _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


def key_event(vk, down):
    scan = _user32.MapVirtualKeyW(vk, 0)
    inp = _INPUT(type=_INPUT_KEYBOARD)
    inp.ki = _KEYBDINPUT(0, scan, _KEYEVENTF_SCANCODE | (0 if down else _KEYEVENTF_KEYUP), 0, None)
    _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


# 键名 → VK（体验区够用的小集合；要更多键后续扩表）
VK = {name: ord(name.upper()) for name in "abcdefghijklmnopqrstuvwxyz0123456789"}
VK.update({"space": 0x20, "shift": 0x10, "ctrl": 0x11, "alt": 0x12, "tab": 0x09,
           "enter": 0x0D, "esc": 0x1B, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27})
VK.update({f"f{i}": 0x70 + i - 1 for i in range(1, 13)})   # F1-F12（ADR-030 键盘映射）
VK.update({"capslock": 0x14, "backspace": 0x08, "delete": 0x2E,
           "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22})


def _appdata():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    os.makedirs(os.path.join(base, "Apex5Unleashed"), exist_ok=True)
    return os.path.join(base, "Apex5Unleashed", "softmap.json")


def _curve(v):
    """官方加速曲线：v>2 后 2 + 2*((v-2)/2)^1.3。"""
    if v > CURVE_THRESHOLD:
        return CURVE_THRESHOLD + 2.0 * ((v - CURVE_THRESHOLD) / 2.0) ** CURVE_EXP
    return v


class GyroAim:
    """体感→鼠标（软件层）。激活：always 或拓展键名（m1..m6/lm/rm，吃 0xEF 位图事件）。"""

    DEFAULTS = {"enabled": False, "sens": 50, "gain": 15.0, "yaw_axis": "z",
                "pitch_axis": "x", "invert_x": False, "invert_y": False,
                "activation": "always", "activation_key": "m1"}

    def __init__(self, cfg_path=None):
        self.cfg_path = cfg_path or _appdata()
        self.cfg = dict(self.DEFAULTS)
        self._load()
        self._lock = threading.Lock()
        self._active = False
        self._last_t = None
        self.stats = {"frames": 0, "last_gyro": [0, 0, 0], "last_accel": [0, 0, 0],
                      "last_send": 0.0, "rate": 0.0}

    def _load(self):
        try:
            with open(self.cfg_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.cfg = {**self.DEFAULTS, **d.get("gyro", {})}
        except Exception:
            pass

    def _save(self):
        try:
            with open(self.cfg_path, "w", encoding="utf-8") as f:
                json.dump({"gyro": self.cfg}, f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    def set_config(self, patch):
        with self._lock:
            self.cfg.update(patch)
            self._save()
        return self.status()

    def on_key(self, keys):
        """0xEF 位图变化回调：keys = 按下的拓展键名列表。"""
        with self._lock:
            if self.cfg["activation"] == "key":
                self._active = self.cfg["activation_key"] in keys

    def on_motion(self, m):
        cfg = self.cfg
        # 遥测常开：不管功能开没开，帧率/原始值都记录——面板上的「手柄到底有没有体感」
        # 自检就靠它（2026-09-21，此前 enabled=False 提前 return 导致 frames 恒 0）
        with self._lock:
            self.stats["frames"] += 1
            self.stats["last_gyro"] = m["gyro"]
            self.stats["last_accel"] = m["accel"]
            now = m["t"]
            dt = now - self._last_t if self._last_t else 0
            self._last_t = now
            if dt > 0:
                self.stats["rate"] = 0.9 * self.stats["rate"] + 0.1 * (1.0 / dt) if self.stats["rate"] else 1.0 / dt
        if not cfg["enabled"]:
            return
        if cfg["activation"] == "key" and not self._active:
            return
        if dt <= 0 or dt > 0.2:
            return
        gx, gy, gz = m["gyro"]
        axis = {"x": gx, "y": gy, "z": gz}
        yaw_raw = axis.get(cfg["yaw_axis"], 0)
        pitch_raw = axis.get(cfg["pitch_axis"], 0)
        dx = self._disp(yaw_raw, dt) * (-1 if cfg["invert_x"] else 1)
        dy = self._disp(pitch_raw, dt) * (-1 if cfg["invert_y"] else 1)
        if dx or dy:
            mouse_move(dx, dy)
            self.stats["last_send"] = time.time()

    def _disp(self, raw, dt):
        """raw → 像素位移：死区/曲线/灵敏度（官方三件套）× 增益（自标定）。"""
        if abs(raw) < GYRO_DEADZONE_RAW:
            return 0.0
        v = _curve(abs(raw) * GYRO_SCALE)
        return (1 if raw > 0 else -1) * v * (self.cfg["sens"] / 50.0) * self.cfg["gain"] * dt

    def status(self):
        with self._lock:
            return {"cfg": dict(self.cfg), "stats": dict(self.stats), "active": self._active}


class StickMap:
    """摇杆→鼠标/WASD（软件层）。中心死区外按偏移比例输出；键盘模式 8 向滞回。"""

    DEFAULTS = {"enabled": False, "stick": "left", "mode": "keys", "deadzone": 3000,
                "sens": 40.0, "keys": {"up": "w", "down": "s", "left": "a", "right": "d"}}

    def __init__(self, cfg_path=None):
        self.cfg_path = cfg_path or _appdata()
        self.cfg = dict(self.DEFAULTS)
        try:
            with open(self.cfg_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.cfg = {**self.DEFAULTS, **d.get("stickmap", {})}
        except Exception:
            pass
        self._pressed = set()
        self._lock = threading.Lock()
        self.stats = {"last_xy": [0, 0], "pressed": []}

    def _save(self):
        try:
            with open(self.cfg_path, "w", encoding="utf-8") as f:
                json.dump({"stickmap": self.cfg}, f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    def set_config(self, patch):
        with self._lock:
            self.cfg.update(patch)
            self._save()
        return self.status()

    def _release_all(self):
        for name in list(self._pressed):
            if name in VK:
                key_event(VK[name], False)
        self._pressed.clear()

    def on_motion(self, m):
        cfg = self.cfg
        if not cfg["enabled"]:
            if self._pressed:
                self._release_all()
            return
        x, y = (m["lx"], m["ly"]) if cfg["stick"] == "left" else (m["rx"], m["ry"])
        with self._lock:
            self.stats["last_xy"] = [x, y]
        mag = (x * x + y * y) ** 0.5
        dz = cfg["deadzone"]
        if mag <= dz:
            if self._pressed:
                self._release_all()
            return
        nx, ny = x / STICK_MAX, -y / STICK_MAX      # 摇杆 Y 上负 → 屏幕上正
        if cfg["mode"] == "mouse":
            mouse_move(nx * cfg["sens"], ny * cfg["sens"])
            return
        want = set()
        th = dz / STICK_MAX + 0.25
        if ny > th:
            want.add(cfg["keys"].get("up"))
        if ny < -th:
            want.add(cfg["keys"].get("down"))
        if nx < -th:
            want.add(cfg["keys"].get("left"))
        if nx > th:
            want.add(cfg["keys"].get("right"))
        want.discard(None)
        for name in want - self._pressed:
            if name in VK:
                key_event(VK[name], True)
        for name in self._pressed - want:
            if name in VK:
                key_event(VK[name], False)
        self._pressed = want
        self.stats["pressed"] = sorted(want)

    def status(self):
        with self._lock:
            return {"cfg": dict(self.cfg), "stats": dict(self.stats)}


class SoftMapHub:
    """运动分发中心：引擎 motion 回调 → 各消费者；拓展键事件 → 激活态。"""

    def __init__(self):
        self.gyro = GyroAim()
        self.stickmap = StickMap()

    def on_motion(self, m):
        for c in (self.gyro, self.stickmap):
            try:
                c.on_motion(m)
            except Exception:
                pass

    def on_key(self, evt):
        keys = evt.get("keys", [])
        try:
            self.gyro.on_key(keys)
        except Exception:
            pass


HUB = SoftMapHub()
