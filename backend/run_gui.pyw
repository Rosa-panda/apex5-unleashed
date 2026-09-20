# 无控制台启动器（pythonw 专用）：stdout/stderr 重定向到日志文件
# 桌面快捷方式 → pythonw.exe run_gui.pyw
import faulthandler
import os
import sys
import time

_t0 = time.perf_counter()
def _phase(name):
    print(f"[boot] {name} +{(time.perf_counter() - _t0) * 1000:.0f}ms", flush=True)

_base = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_base, "app"))
_log = open(os.path.join(_base, "apex5.log"), "w", encoding="utf-8", buffering=1)
faulthandler.enable(file=_log)            # 原生崩溃留痕（2026-09-20 后台无声死亡，无迹可查）
sys.stdout = _log
sys.stderr = _log
sys.argv = [sys.argv[0]]
_phase("launcher start")

from main import main  # noqa: E402
_phase("imports done")                    # 冷启动大头候补：uvicorn/webview/fastapi 导入

main()
