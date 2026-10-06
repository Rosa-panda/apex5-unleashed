#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""推送前自检（pre-push gate）——本地镜像 ci.yml test job 的四道门禁 + 版本一致性。

为什么存在：2026-10-06 推送 6 个提交后 CI 连环红（pytest 收集崩 / cp1252 编码 / 版本双文件
不同步），根因是「改完直接 push，门禁靠 CI 兜底」。CI 是硬门禁不会取消，但反馈慢；
**推送前跑一遍本脚本，60~120 秒内拿到与 CI 等价的结论**。

用法（仓库根执行）：
    python tools/prepush_check.py            # 全部四步 + 版本一致性
    python tools/prepush_check.py --quick    # 跳过冒烟与前端构建（最快路径，CI 仍会全跑）

⚠ 与 ci.yml 的同步纪律：ci.yml test job 的步骤增删时**必须同步本脚本**（反之亦然），
两边清单以 ci.yml 为真相源。
"""
import subprocess
import sys
import time

STEPS = [
    # (名称, 命令列表, 是否可 --quick 跳过)
    ("版本一致性（VERSION ↔ package.json）",
     ["python", "tools/check_version.py"], False),
    ("pytest 单测（收集排除见 backend/conftest.py）",
     ["python", "-m", "pytest", "backend", "-q"], False),
    ("脚本式单测（纯 Mock 名单）",
     ["python", "tools/run_script_tests.py"], False),
    ("Mock 全链路冒烟",
     ["python", "tools/run_smoke.py"], True),
    ("前端构建",
     ["npm", "run", "build"], True),
]


def main(argv=None) -> int:
    quick = "--quick" in (argv or [])
    failed = []
    for name, cmd, skippable in STEPS:
        if quick and skippable:
            print(f"− 跳过 {name}（--quick）")
            continue
        print(f"▶ {name} ...", flush=True)
        t0 = time.time()
        try:
            r = subprocess.run(cmd)
        except FileNotFoundError as e:
            print(f"  ✗ 命令不存在：{e}")
            failed.append(name)
            continue
        dt = time.time() - t0
        ok = r.returncode == 0
        print(f"  {'✓' if ok else '✗'} {name}（{dt:.0f}s）\n", flush=True)
        if not ok:
            failed.append(name)
    print("=" * 46)
    if failed:
        print(f"✗ {len(failed)} 项未过：{'、'.join(failed)}——先修复再 push（CI 是同一套门禁，红了照样不发版）")
        return 1
    print("✓ 全部通过——可以 push（CI 会再跑同一套门禁并自动发版）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
