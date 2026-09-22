# 测试台端点（ADR-029 B7 自 service.py 逐字搬出）：震动脉冲/正弦/拓展键归因校准。
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel


def build_testbench_router(ctx):
    r = APIRouter()
    engine = ctx.engine

    @r.post("/api/test/pulse")
    def test_pulse():
        engine.test_pulse()
        return {"ok": True}

    class SineReq(BaseModel):
        seconds: float = 3.0
        freq: float = 3.0
        amp: int = 220

    @r.post("/api/test/sine")
    def test_sine(req: SineReq):
        engine.test_sine(req.seconds, req.freq, req.amp)
        return {"ok": True}

    @r.post("/api/test/attrib")
    def test_attrib():
        """拓展键受控校准：每键独立时间窗采集 bit→键名归因（进度走 WS attrib 事件）。"""
        import keymonitor
        mon = keymonitor.GamepadRawMonitor.ACTIVE
        if mon is None:
            return JSONResponse({"error": "游戏盘原始监听未运行（mock 模式或设备未连）"}, status_code=400)
        if not mon.start_attribution():
            return JSONResponse({"error": "校准已在进行中"}, status_code=409)
        return {"ok": True}

    @r.get("/api/test/keymap")
    def test_keymap():
        import keymonitor
        mon = keymonitor.GamepadRawMonitor.ACTIVE
        return {"running": bool(mon and mon._attrib_running),
                "labels": {f"b{b}.{bit}": name for (b, bit), name in load_labels_items()}}

    def load_labels_items():
        import keymonitor
        try:
            mon = keymonitor.GamepadRawMonitor.ACTIVE
            if mon:
                return mon._labels.items()
        except Exception:
            pass
        return keymonitor.load_labels().items()

    return r
