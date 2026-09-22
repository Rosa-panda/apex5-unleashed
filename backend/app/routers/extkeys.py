# 拓展键端点（ADR-029 B4 自 service.py 逐字搬出；原 ADR-019：映射读写 + 测试模式）
from fastapi import APIRouter
from pydantic import BaseModel

from .common import err


def build_extkeys_router(ctx):
    r = APIRouter()

    @r.get("/api/extkeys")
    def extkeys_get():
        import extkeys
        try:
            return {"ok": True, "keys": extkeys.MAPPER.read_mapping()}
        except Exception as e:
            return err(e)

    class ExtKeysTestReq(BaseModel):
        on: bool

    @r.post("/api/extkeys/testmode")
    def extkeys_testmode(req: ExtKeysTestReq):
        """测试模式：六键映射到 Gamepad API 可见目标（视图/菜单/LB/RB/L3/R3）；关=还原备份。"""
        import extkeys
        try:
            if req.on:
                return extkeys.MAPPER.set_targets(extkeys.TEST_TARGETS)
            return extkeys.MAPPER.restore()
        except Exception as e:
            return err(e)

    return r
