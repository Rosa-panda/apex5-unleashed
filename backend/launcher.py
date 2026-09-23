# 打包版启动器（PyInstaller --noconsole 专用入口）：
# stdout/stderr → %APPDATA%\Apex5Unleashed\apex5.log（安装目录可能只读，APPDATA 恒可写）。
# 开发态请走 run_gui.pyw（日志在 backend/ 下）；本文件只为 frozen 产物服务。
import faulthandler
import os
import sys
import time

_t0 = time.perf_counter()


def _phase(name):
    print(f"[boot] {name} +{(time.perf_counter() - _t0) * 1000:.0f}ms", flush=True)


_base = os.environ.get("APPDATA") or os.path.expanduser("~")
_d = os.path.join(_base, "Apex5Unleashed")
os.makedirs(_d, exist_ok=True)
_log = open(os.path.join(_d, "apex5.log"), "w", encoding="utf-8", buffering=1)
faulthandler.enable(file=_log)            # 原生崩溃留痕（与 run_gui.pyw 同策略）
sys.stdout = _log
sys.stderr = _log
if not getattr(sys, "frozen", False):     # 源码态误运行本文件时也能起（开发兜底）
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))
_phase("launcher start")

from main import main  # noqa: E402
_phase("imports done")

main()
