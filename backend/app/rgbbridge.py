# DSX(DualSenseX) RGB UDP 桥（ADR-027，体验区 #8）：监听 127.0.0.1:7878，
# 把游戏发来的纯色 RGBUpdate 翻译成手柄灯效（驻留灯表写）。
# 协议事实（RESEARCH §E / ADR-025）：DSX UDP 报文为 ASCII 指令，RGBUpdate 的
# parameters 以 r,g,b 开头；格式变体一律进 unknown 计数（真机期对照 dsxingress 补全）。
import ast
import socket
import threading
import time

DEFAULT_PORT = 7878
MIN_INTERVAL = 1.0           # 灯表写是 flash 驻留操作，限频
ALLOW_HOSTS = {"127.0.0.1", "::1"}


class RgbBridge:
    def __init__(self, engine, port=DEFAULT_PORT):
        self.engine = engine
        self.port = port
        self.enabled = False
        self._sock = None
        self._thread = None
        self._stop = threading.Event()
        self._last_apply = 0.0
        self._last_rgb = None
        self.stats = {"packets": 0, "applied": 0, "throttled": 0, "unknown": 0,
                      "last_error": None, "last_rgb": None, "note": None}

    def start(self, port=None):
        if self.enabled:
            return self.status()
        requested = int(port or self.port)
        self._stop.clear()
        # 7878 常被飞智自家 SpaceStationService 独占（0.0.0.0:7878，WinError 10013），
        # 绑不上就顺延找空位，把实际端口回显给前端（2026-09-20 真机撞上过）。
        self._sock = None
        last_err = None
        for p in range(requested, requested + 20):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.bind(("127.0.0.1", p))
            except OSError as e:
                last_err = e
                continue
            self._sock = s
            self.port = p
            break
        if self._sock is None:
            raise OSError(f"UDP {requested}..{requested + 19} 全被占用，最后错误：{last_err}")
        self._sock.settimeout(0.5)
        self._thread = threading.Thread(target=self._loop, daemon=True, name="rgbbridge")
        self._thread.start()
        self.enabled = True
        if self.port != requested:
            self.stats["note"] = (f"请求端口 {requested} 被占用（多半是飞智空间站服务），"
                                  f"实际监听 {self.port}——游戏/DSX 那边请指向 {self.port}")
        else:
            self.stats["note"] = None
        return self.status()

    def stop(self):
        self._stop.set()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        self._sock = None
        self.enabled = False
        return self.status()

    def _loop(self):
        while not self._stop.is_set():
            try:
                data, addr = self._sock.recvfrom(512)
            except socket.timeout:
                continue
            except OSError:
                break
            if addr[0] not in ALLOW_HOSTS:
                continue
            self.stats["packets"] += 1
            rgb = self._parse(data)
            if rgb is None:
                self.stats["unknown"] += 1
                continue
            self.stats["last_rgb"] = rgb
            now = time.monotonic()
            if rgb == self._last_rgb and now - self._last_apply < 10.0:
                continue                       # 同色不重写
            if now - self._last_apply < MIN_INTERVAL:
                self.stats["throttled"] += 1
                continue
            try:
                on = rgb != (0, 0, 0)
                self.engine.led_apply_effect("on" if on else "off", rgb, source="rgbbridge")
                self._last_apply = now
                self._last_rgb = rgb
                self.stats["applied"] += 1
            except Exception as e:
                self.stats["last_error"] = f"{type(e).__name__}: {e}"

    def _parse(self, data):
        """'255,0,128' / '2|255,0,128' / 任意含前三个整数的 ASCII → (r,g,b)。"""
        try:
            text = data.decode("ascii", "ignore")
            nums = ast.literal_eval("[" + text.replace("|", ",").replace(";", ",") + "]")
        except Exception:
            return None
        vals = [int(n) for n in nums if isinstance(n, int) and 0 <= n <= 255]
        if len(vals) < 3:
            return None
        return tuple(vals[:3])

    def status(self):
        return {"enabled": self.enabled, "port": self.port, "stats": dict(self.stats)}
