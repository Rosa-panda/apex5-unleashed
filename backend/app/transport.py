# 传输层：真机 HidPad / MockPad 抽象（ADR-011）。future: TracePad 回放挂这层
import threading
import time
from collections import deque

import protocol


class MockPad:
    """无手柄时的假设备：write 后 5ms 生成合法 ACK。全链路离线可开发。"""
    kind = "mock"

    def __init__(self):
        self._inbox = deque()          # (due_ts, frame)
        self._lock = threading.Lock()

    def write(self, buf):
        cmd = buf[3]
        with self._lock:
            self._inbox.append((time.monotonic() + 0.005, protocol.mock_ack_frame(cmd)))
        return len(buf)

    def read(self, timeout_ms):
        deadline = time.monotonic() + timeout_ms / 1000.0
        while True:
            with self._lock:
                if self._inbox and self._inbox[0][0] <= time.monotonic():
                    return self._inbox.popleft()[1]
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.001)

    def close(self):
        pass


class HidPad:
    """真机 vendor 接口。注意：整个进程只允许存在一个实例（ADR-012）。"""
    kind = "real"

    def __init__(self, path):
        import hid
        self.d = hid.device()
        self.d.open_path(path)

    def write(self, buf):
        return self.d.write(bytes(buf))

    def read(self, timeout_ms):
        return self.d.read(64, timeout_ms=timeout_ms)

    def close(self):
        try:
            self.d.close()
        except Exception:
            pass


def find_device_path():
    try:
        import hid
    except ImportError:
        return None
    try:
        for dev in hid.enumerate(protocol.VID, protocol.PID):
            if dev.get("usage_page") == protocol.USAGE_PAGE_VENDOR:
                return dev["path"]
    except Exception:
        return None
    return None
