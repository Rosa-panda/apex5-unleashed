#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""Mock 全链路冒烟的服务编排器（T03.3）。

`backend/smoke_test.py` 本身是一个「连着运行中后端」的冒烟脚本，必须有人先把服务跑起来。
本脚本把「起服务 → 等就绪 → 跑冒烟 → 收尾杀进程」串成一条命令，于是 CI 可以一行纳入门禁：

    python tools/run_smoke.py                 # 默认端口 18799
    python tools/run_smoke.py --port 18800    # 手动指定端口

设计要点（踩过的坑都写在注释里）：

1. **必须避开默认端口 18765**：`backend/run.py` 有单实例逻辑——发现 18765 已有实例会去
   `/api/show` 唤起它然后自己退出，于是「新起的服务」根本不存在，冒烟连的是别人的实例。
2. **收尾必须用 `terminate()` 而不是 SIGINT**：`--no-gui` 分支是 `while True: sleep(1)`，
   只在 KeyboardInterrupt 时收尾；Windows 上 `terminate()` 走 TerminateProcess，干净利落。
   `CTRL_BREAK` / SIGINT 在 CI runner 上不可靠。
3. **就绪轮询超时要大（默认 40s）**：端口冲突时 `run.py` 最多重试 12s 才报错，超时给小了会误判。
4. 子进程 stdout/stderr 直接继承（CI 里要看到弄错的内幕）；返回码即 subprocess 的返回码。

退出码：0 = ALL SMOKE OK；1 = 冒烟失败；2 = 服务未能就绪 / 端口被占。
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """端口探测：连得上就说明有人占着（本机 http 服务握手前也会接受连接）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def wait_health(base: str, timeout: float) -> bool:
    """轮询 GET {base}/api/health 直到 ok=True。"""
    deadline = time.time() + timeout
    url = base + "/api/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2.0) as resp:
                if json.loads(resp.read()).get("ok"):
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="起 Mock 服务 → 跑 smoke_test → 收尾")
    ap.add_argument("--port", type=int,
                    default=int(os.environ.get("APEX5_SMOKE_PORT", "18799")),
                    help="Mock 服务端口（默认 18799，避开单实例默认端口 18765）")
    ap.add_argument("--timeout", type=float, default=40.0,
                    help="等待服务就绪的秒数（默认 40，需大于 run.py 的 12s 端口重试）")
    args = ap.parse_args(argv)

    port = args.port
    base = "http://127.0.0.1:{}".format(port)
    cwd = REPO_ROOT

    if port_in_use(port):
        print("[run_smoke] 端口 {} 已被占用，换一个：python tools/run_smoke.py --port N".format(port))
        return 2

    print("[run_smoke] 启动 Mock 服务：python backend/run.py --mock --no-gui --port {}".format(port))
    proc = subprocess.Popen(
        [sys.executable, "backend/run.py", "--mock", "--no-gui", "--port", str(port)],
        cwd=cwd,
    )
    try:
        if not wait_health(base, args.timeout):
            print("[run_smoke] 服务在 {}s 内未就绪".format(args.timeout))
            return 2
        print("[run_smoke] 服务就绪：{}".format(base))

        env = dict(os.environ, APEX5_BASE=base)
        rc = subprocess.run(
            [sys.executable, "backend/smoke_test.py"],
            cwd=cwd, env=env,
        ).returncode
        if rc != 0:
            print("[run_smoke] 冒烟失败（returncode={}）".format(rc))
        else:
            print("[run_smoke] ALL SMOKE OK")
        return rc
    finally:
        if proc.poll() is None:
            proc.terminate()          # Windows → TerminateProcess，不用 SIGINT
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        # 端口释放可能有短暂 TIME_WAIT，CI 里连续跑不同端口才安全
        print("[run_smoke] 服务已停止（pid={}）".format(proc.pid))


if __name__ == "__main__":
    sys.exit(main())
