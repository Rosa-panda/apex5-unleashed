# 灯光端点（ADR-029 B3 自 service.py 逐字搬出；原 ADR-018）
from fastapi import APIRouter
from pydantic import BaseModel

import protocol

from .common import err


def build_led_router(ctx):
    r = APIRouter()
    engine = ctx.engine

    class LedTestReq(BaseModel):
        r: int = 255
        g: int = 0
        b: int = 0

    @r.post("/api/led/test")
    def led_test(req: LedTestReq):
        try:
            engine.led_test(req.r, req.g, req.b)
            return {"ok": True}
        except Exception as e:
            return err(e)

    @r.get("/api/led/config")
    def led_config():
        try:
            import base64
            bean = engine.led_read_config(source="ui")
            detect = frames_b64 = None
            if bean is not None and engine._led_blob_raw:
                try:
                    detect = protocol.led_identify(engine._led_blob_raw)
                except Exception:
                    detect = None                   # 识别失败不挡配置读取
                frames_b64 = base64.b64encode(engine._led_blob_raw[20:]).decode("ascii")
            return {"ok": bean is not None, "bean": bean,
                    "detect": detect, "frames_b64": frames_b64}
        except Exception as e:
            return err(e)

    class LedApplyReq(BaseModel):
        mode: str                       # on/off/breath/gradient/flow/default
        colors: list = [[255, 0, 0]]    # [[r,g,b], ...]
        brightness: int | None = None
        period: int | None = None

    @r.post("/api/led/apply")
    def led_apply(req: LedApplyReq):
        try:
            engine.led_apply_effect(req.mode, [tuple(c) for c in req.colors],
                                    brightness=req.brightness, period=req.period)
            return {"ok": True}
        except Exception as e:
            return err(e)

    @r.post("/api/led/backup")
    def led_backup():
        try:
            return {"ok": True, "path": engine.led_backup()}
        except Exception as e:
            return err(e)

    @r.post("/api/led/restore")
    def led_restore():
        try:
            engine.led_restore()
            return {"ok": True}
        except Exception as e:
            return err(e)

    return r
