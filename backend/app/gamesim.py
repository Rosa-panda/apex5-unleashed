# 模拟游戏场（体验区 #16，ADR-027 附加）：不下真游戏，模拟游戏事件联调全链路。
# 发包走真实链路（与官方 Mod / DSX 生态同端口同格式）：
#   DSX 协议 JSON → 127.0.0.1:{ingress.port} → cmd51 扳机（+灯效桥闪灯钩子）
#   RGB ASCII     → 127.0.0.1:{rgbbridge.port} → 灯表写
# 测试结论可直接迁移到真游戏。注意：ingress 只在工具持有手柄（proxy= self）时写出。
import json
import math
import random
import socket
import threading
import time

SCENARIOS = {
    "shooting": "射击 6s（右扳机连发震动+灯闪红）",
    "explosion": "爆炸（双扳机猛震+灯闪橙，1.5s）",
    "race": "赛车 8s（扳机油门阻尼起伏）",
    "lowhp": "低血量（灯常亮红）",
    "heal": "回血（灯变绿）",
    "idle": "松开复位（扳机归零+熄灯）",
}

FLYDIGI_MAGIC = 19


def _dsx_pkt(side, mode, params):
    # {"instructions":[{"type":1,"parameters":[手柄号,侧,19,wire模式,p1..p5]}]}（ADR-025）
    return json.dumps({"instructions": [
        {"type": 1, "parameters": [0, side, FLYDIGI_MAGIC, mode] + list(params)}]}).encode("ascii")


def _send_udp(port, data):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.sendto(data, ("127.0.0.1", port))
    finally:
        s.close()


class GameSim:
    def __init__(self, ingress_getter, rgb_getter):
        self._ingress_getter = ingress_getter   # → DsxIngress（.port 可用性见实例）
        self._rgb_getter = rgb_getter           # → RgbBridge
        self.scenario = None                    # 运行中的场景名（None=空闲）
        self._stop = threading.Event()
        self._thread = None
        self.stats = {"runs": 0, "dsx_sent": 0, "rgb_sent": 0,
                      "last_scenario": None, "note": None}

    # ---------- 发送原语（不存在目标时记 note 不炸） ----------
    def _dsx(self, side, mode, params):
        ing = self._ingress_getter()
        if not ing or not ing.port:
            self.stats["note"] = "DSX ingress 未启动（重启工具自动拉起；7878/8787 被占则起不来）"
            return False
        try:
            _send_udp(ing.port, _dsx_pkt(side, mode, params))
            self.stats["dsx_sent"] += 1
            return True
        except OSError as e:
            self.stats["note"] = f"发往 ingress 失败：{e}"
            return False

    def _rgb(self, r, g, b):
        rgb = self._rgb_getter()
        if not rgb or not rgb.enabled:
            self.stats["note"] = "灯效桥未启动（体验区 → Mod 灯效桥 → 启动）"
            return False
        try:
            _send_udp(rgb.port, f"{r},{g},{b}".encode("ascii"))
            self.stats["rgb_sent"] += 1
            return True
        except OSError as e:
            self.stats["note"] = f"发往灯效桥失败：{e}"
            return False

    def _trig(self, side, mode, params):
        # strength 带随机抖动：beat 掉 ingress 去重，模拟真游戏的连续变化
        p = list(params)
        if p:
            p[2] = max(1, p[2] + random.randint(-15, 15))
        return self._dsx(side, mode, p)

    # ---------- 生命周期 ----------
    def start(self, scenario):
        if scenario not in SCENARIOS:
            raise ValueError(f"未知场景：{scenario}")
        self.stop()
        self._stop.clear()
        self.scenario = scenario
        self._thread = threading.Thread(
            target=self._run, args=(scenario,), daemon=True, name=f"gamesim-{scenario}")
        self._thread.start()
        return self.status()

    def stop(self):
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)
        self._thread = None
        self.scenario = None

    def _run(self, scenario):
        self.stats["runs"] += 1
        self.stats["last_scenario"] = scenario
        self.stats["note"] = None
        try:
            getattr(self, f"_sc_{scenario}")()
        finally:
            self.scenario = None

    def _wait(self, seconds):
        if self._stop.wait(seconds):
            raise InterruptedError

    # ---------- 场景 ----------
    def _sc_shooting(self):
        """射击：右扳机 120ms 连发脉冲（wire5 震动），灯每 1.2s 红/暗交替。"""
        self._rgb(255, 0, 0)
        t_end = time.monotonic() + 6
        tick = 0
        while time.monotonic() < t_end:
            self._trig(2, 5, [10, 60, 120, 40, 1])          # 右扳机震动
            tick += 1
            if tick % 10 == 0:                               # ~1.2s
                self._rgb(0, 0, 0) if tick % 20 == 0 else self._rgb(255, 0, 0)
            self._wait(0.12)
        self._dsx(2, 0, [])                                  # 松开

    def _sc_explosion(self):
        """爆炸：双扳机猛震 + 橙灯，1.2s 后松开熄灯。"""
        self._rgb(255, 120, 0)
        self._trig(1, 5, [10, 255, 200, 30, 1])
        self._trig(2, 5, [10, 255, 200, 30, 1])
        self._wait(1.2)
        self._dsx(1, 0, [])
        self._dsx(2, 0, [])
        self._rgb(0, 0, 0)

    def _sc_race(self):
        """赛车：扳机油门阻尼正弦起伏（wire1 race），8s 后归零。"""
        self._dsx(1, 1, [255, 80, 1])                        # 左：固定轻阻尼
        t_end = time.monotonic() + 8
        while time.monotonic() < t_end:
            res = int(60 + 80 * (1 + math.sin(time.monotonic() * 1.5)) / 2)   # 60..140
            self._trig(2, 1, [255, res, 1])                  # 右：油门阻尼起伏
            self._wait(0.1)
        self._dsx(1, 0, [])
        self._dsx(2, 0, [])

    def _sc_lowhp(self):
        self._rgb(255, 0, 0)

    def _sc_heal(self):
        self._rgb(0, 255, 0)

    def _sc_idle(self):
        self._dsx(1, 0, [])
        self._dsx(2, 0, [])
        self._rgb(0, 0, 0)

    def status(self):
        return {"running": self.scenario, "scenarios": dict(SCENARIOS),
                "stats": dict(self.stats)}
