# routers 公共帮手（ADR-029 B2；B7 增 _require_real/_full_backup，自 service.py 搬入）
from fastapi.responses import JSONResponse


def err(e):
    return JSONResponse({"error": str(e)}, status_code=400)


def require_real(engine):
    if engine.force_mock or engine.dev_kind != "real":
        raise RuntimeError("此操作需要真机连接（mock 模式不可用）")


def full_backup(engine):
    """危险操作前的全量备份：四槽 blob + 灯表 → %APPDATA%\\Apex5Unleashed\\backup_<ts>\\。"""
    import os
    import time
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "Apex5Unleashed",
                     "backup_" + time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(d, exist_ok=True)
    import extkeys
    import profile as _profile
    with _profile.SERVICE._lock:
        pad = extkeys.Pad()
        st = pad.read_status()
        for i in range(_profile.SLOTS):
            blob = _profile.SERVICE._read_live(pad, i)
            with open(os.path.join(d, f"slot{i}.bin"), "wb") as f:
                f.write(bytes(blob))
    try:
        engine.led_backup(os.path.join(d, "led.bin"))
    except Exception:
        pass
    with open(os.path.join(d, "README.txt"), "w", encoding="utf-8") as f:
        f.write(f"恢复出厂前自动全量备份 {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"slot0-3.bin=档案blob  led.bin=灯表（读不到则无此文件）\n")
    return d
