# -*- coding: utf-8 -*-
"""pytest 兜底配置（T03.2）。

`backend/smoke_test.py` 的文件名命中 pytest 默认收集规则（`test_*.py`），但它在**模块级**
`asyncio.run(main())` 直连 `127.0.0.1:18765` —— 直接 import 就会 ConnectionRefusedError，
连带让整个 pytest 进程在收集阶段崩掉（ARCHITECTURE §7 偏差 D8）。

这里用 `collect_ignore_glob` 永久排除它，于是 `python -m pytest backend -q` 在任何目录下跑都安全；
冒烟请走 `tools/run_smoke.py`（自动起 Mock 服务 → 跑冒烟 → 收尾杀进程）。

注：本文件必须放 `backend/`（pytest 的 rootdir/测试根），**不能**放 `backend/app/` ——
app 是被 `sys.path.insert` 塞进来的模块目录，不是测试根。
"""
import os

# 相对本 conftest 所在目录匹配（`backend/smoke_test.py`）
collect_ignore_glob = [
    "smoke_test.py",
    # 脚本式门禁（T03.4）：模块级 assert + 硬依赖本机飞智空间站出厂 bin，
    # pytest 收集即崩（CI 实锤 2026-10-06）。CI 名单由 tools/run_script_tests.py 管。
    "test_screen_offline.py",
]

# 保险：绝对路径也列一遍，避免将来有人改动收集根目录时漏掉
collect_ignore = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "smoke_test.py"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_screen_offline.py"),
]
