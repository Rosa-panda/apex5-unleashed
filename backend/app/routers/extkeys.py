# 拓展键端点（ADR-029 B4 自 service.py 逐字搬出；原 ADR-019：映射读写 + 测试模式；
# ADR-030：完整映射双通道——gamepad 走固件表，keyboard 走软件 SendInput）
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

    # ---- ADR-030：完整映射 ----
    @r.get("/api/extkeys/mapping")
    def mapping_get():
        import extkeys
        import extkeymap
        import macro
        try:
            fw = extkeys.MAPPER.read_mapping()
            bound = sorted(m["name"] for m in fw if m["target"] == macro.TARGET_MACRO)
            return {"ok": True, "config": extkeymap.load(),
                    "targets": extkeys.TARGET_NAMES,
                    "macro_bound": bound,
                    "fw": fw}
        except Exception as e:
            return err(e)

    class MappingReq(BaseModel):
        config: dict

    @r.post("/api/extkeys/mapping")
    def mapping_post(req: MappingReq):
        """应用映射：gamepad→固件键表，keyboard/passthrough→透传 255 + 软件注入。"""
        import extkeys
        import extkeymap
        try:
            cfg = extkeymap.sanitize(req.config)
            res = extkeymap.apply(cfg, raw=ctx.raw)
            if ctx.extkeymap is not None:
                ctx.extkeymap.reload()
            return {"ok": True, "config": cfg, "fw": res}
        except Exception as e:
            return err(e)

    return r
