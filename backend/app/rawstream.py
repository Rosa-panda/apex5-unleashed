# 0xEF 位图流按需开关（ADR-028 修订 2，2026-09-22）。
# 流常开 = 固件把 HID 上报当活动、手柄永不断电休眠（用户实锤）。改为需求
# 登记表：消费者活跃才开，全部退场自动关。独立成模块——此前散在 service.py
# 闭包里，靠「定义先于使用」的书写顺序维系，曾因 import 顺序炸过启动。
# 消费者：
#   master  体感总闸（持久态恢复时同样登记）
#   macro   宏录制 start/stop
#   padlive 拓展键监听心跳（前端测试页每 15s 打卡，超时自动收流）
#   manual  /api/exp/imu 手动开关（无 UI，调试用）
# 看门狗周期对账，兜住 macro/profile 写配置后 enable_raw_stream 强开的流。
import threading
import time


class RawStreamHub:
    def __init__(self, engine, timeout=30.0, watchdog_interval=30.0):
        self.engine = engine
        self.timeout = timeout
        self.watchdog_interval = watchdog_interval
        self.demands = {"master": False, "macro": False, "manual": False}
        self.padlive = 0.0          # 拓展键监听最近一次心跳（monotonic），0=无
        self._lock = threading.Lock()

    def heartbeat(self, on=True):
        """拓展键监听打卡：on=False 立即撤需求。"""
        with self._lock:
            self.padlive = time.monotonic() if on else 0.0

    def wanted(self):
        with self._lock:
            fresh = time.monotonic() - self.padlive < self.timeout
        d = self.demands
        return bool(d["master"] or d["macro"] or d["manual"] or fresh)

    def eval(self, source="eval"):
        """按需求决策流开关；只在期望态与实际不一致时下发 cmd17（防重复）。"""
        on = self.wanted()
        if bool(self.engine.raw_motion) != on:
            self.engine.set_raw_motion(on, source=source)
        return on

    def start_watchdog(self):
        def _loop():
            threading.current_thread().name = "raw-watchdog"
            while True:
                time.sleep(self.watchdog_interval)
                if self.engine.online:
                    try:
                        self.eval("watchdog")
                    except Exception:
                        pass
        threading.Thread(target=_loop, daemon=True).start()
