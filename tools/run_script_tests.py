#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""脚本式单测批量执行器（T03.4）。

仓库里有一批**脚本式**单测：模块级 `assert`，跑法是 `python backend/test_<name>.py`，
pytest 收集不到（它们没有 `def test_*`），CI 上等于没跑。本脚本把它们逐个塞进**独立子进程**
隔离跑（一个进程的全局状态不会污染下一个），任一非零退出即整批处理失败：

    python tools/run_script_tests.py            # CI 名单（纯 Mock，可无头跑）
    python tools/run_script_tests.py --local    # 追加本机专属项（需本机装了飞智空间站）
    python tools/run_script_tests.py test_led   # 只跑指定项（前缀匹配）

名单决策（改动前请先读 TEST-PLAN.md「CI 策略 / 排除项」）：

- `test_dsx_mod.py` / `test_rawstream.py` 是 pytest 式（已有 `def test_*`），**不在这里跑**，
  由 `python -m pytest backend -q` 覆盖，避免重复执行。
- `test_grip_real.py` 打运行中后端的 HTTP API，**需真机**，不进 CI（归 T05 真机验收）。
- `test_smoke`/`smoke_test.py` 需运行中服务，走 `tools/run_smoke.py`。
- `test_screen_offline.py` 第 2 项硬依赖本机
  `C:\Program Files\Flydigi Space Station\Configs\Controller\k5\default\default_screen_image_*.bin`
  ——CI runner 上没有官方软件，未安装时它必 AssertionError。故默认不跑，仅 `--local` 时跑。
"""
import argparse
import os
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# CI 名单：全部纯 Mock，无需真机、无需本机专有文件
CI_TESTS = [
    "test_adaptation",
    "test_battery",
    "test_extkeymap",
    "test_games",
    "test_led",
    "test_macro",
    "test_pending_fifo",
    "test_proxy_fix",
    "test_reclaim",
]

# 本机专属：依赖本机环境（官方软件 / 运行中服务），CI 上必挂
LOCAL_ONLY_TESTS = [
    "test_screen_offline",   # 需本机飞智空间站出厂 bin
]

DEFAULT_TIMEOUT = 180.0


def run_one(name: str, timeout: float) -> tuple:
    """跑一个脚本式测试，返回 (ok: bool, seconds: float)。"""
    path = os.path.join("backend", name + ".py")
    abs_path = os.path.join(REPO_ROOT, path)
    if not os.path.isfile(abs_path):
        print("  ✗ {} —— 文件不存在（{}）".format(name, path))
        return False, 0.0
    t0 = time.time()
    proc = subprocess.run(
        [sys.executable, path],
        cwd=REPO_ROOT,
        timeout=timeout,
    )
    dt = time.time() - t0
    ok = proc.returncode == 0
    print("  {} {} ({:.1f}s, returncode={})".format("✓" if ok else "✗", name, dt, proc.returncode))
    return ok, dt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="批量跑 backend 下的脚本式单测")
    ap.add_argument("--local", action="store_true",
                    help="追加本机专属项（需本机安装飞智空间站出厂 bin）")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                    help="单个测试超时秒数（默认 180）")
    ap.add_argument("filter", nargs="*", help="只跑名字含这些子串的测试")
    args = ap.parse_args(argv)

    names = list(CI_TESTS)
    if args.local:
        names += list(LOCAL_ONLY_TESTS)
    if args.filter:
        names = [n for n in names if any(f in n for f in args.filter)]
    if not names:
        print("没有匹配的测试")
        return 1

    print("脚本式单测：共 {} 项{}\n".format(
        len(names), "（含 --local 本机专属项）" if args.local else "（CI 名单）"))

    failed, total_dt = [], 0.0
    for name in names:
        try:
            ok, dt = run_one(name, args.timeout)
        except subprocess.TimeoutExpired:
            print("  ✗ {} —— 超时（{}s）".format(name, args.timeout))
            ok, dt = False, args.timeout
        total_dt += dt
        if not ok:
            failed.append(name)

    print("\n汇总：{} 通过 / {} 失败 / 共 {} 项，耗时 {:.1f}s".format(
        len(names) - len(failed), len(failed), len(names), total_dt))
    if failed:
        print("失败项：{}".format(", ".join(failed)))
        return 1
    print("ALL SCRIPT TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
