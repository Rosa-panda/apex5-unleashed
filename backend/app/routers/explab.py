# 体验区端点（ADR-029 B7 自 service.py 逐字搬出；ADR-026 注册表/判定 + ADR-027
# 非体感功能端点：档案/槽位/恢复出厂/devcfg/owner/瞄准映射/灯桥开关/迷宫/DSU/分享码/诊断）。
# 体感类端点（imu/rawstream/总闸/gamesim/灯桥 flash+test）在 routers/motion.py（B8）。
from fastapi import APIRouter
from pydantic import BaseModel

from .common import err, require_real, full_backup


def build_explab_router(ctx):
    r = APIRouter()
    engine = ctx.engine
    verdicts = ctx.exp_verdicts
    settings_writer = ctx.settings_writer
    rgb = ctx.rgb
    diag_svc = ctx.diag
    maze_svc = ctx.maze
    dsu_svc = ctx.dsu

    import explab as _explab

    class ExpVerdictReq(BaseModel):
        id: str
        verdict: str          # good / bad / pending
        note: str = ""

    @r.get("/api/exp")
    def exp_list():
        """注册表 + 判定合并下发：前端卡片全靠这里渲染，不硬编码。"""
        feats = []
        for f in _explab.FEATURES:
            v = verdicts.get(f["id"])
            feats.append({**f, "tierLabel": _explab.TIER_LABEL[f["tier"]],
                          "verdict": v.get("verdict", "pending"),
                          "note": v.get("note", "")})
        return {"ok": True, "features": feats, "summary": verdicts.summary()}

    @r.post("/api/exp/verdict")
    def exp_verdict(req: ExpVerdictReq):
        """真机测试后的判定留痕：转正/淘汰的证据链。"""
        if not any(f["id"] == req.id for f in _explab.FEATURES):
            return err(ValueError(f"未知体验区功能: {req.id}"))
        try:
            v = verdicts.set(req.id, req.verdict, req.note)
        except Exception as e:
            return err(e)
        return {"ok": True, "id": req.id, **v, "summary": verdicts.summary()}

    class ExpTurboReq(BaseModel):
        kid: int
        mode: int            # 0 关 / 1 按住连发 / 2 开关切换
        freq: int = 10

    class ExpStickReq(BaseModel):
        side: str
        preset: int | None = None
        center: int = 0
        edge: int = 0
        p1: list[int] = [63, 63]
        p2: list[int] = [127, 127]
        is_round: bool | None = None

    class ExpTriggerCurveReq(BaseModel):
        side: str
        zero: int = 0
        end: int = 255

    class ExpMotionReq(BaseModel):
        target: int
        enable_key: int = 255
        enable_type: int = 0
        dead_zone: int = 10
        sens_x: int = 50
        sens_y: int = 50

    class ExpGripVibReq(BaseModel):
        enabled: bool
        left: dict = {}
        right: dict = {}

    class ExpTitleReq(BaseModel):
        title: str

    class ExpSettingReq(BaseModel):
        op: str              # bit / rate / precision / sensitivity / sleep
        sub: int | None = None
        on: bool | None = None
        value: int | None = None

    class ExpNicknameReq(BaseModel):
        name: str

    class ExpSlotReq(BaseModel):
        slot: int
        confirm: str = ""

    class ExpShareReq(BaseModel):
        code: str = ""
        kind: str = "profile"
        blob_hex: str = ""

    class ExpGyroReq(BaseModel):
        patch: dict = {}

    class ExpRgbReq(BaseModel):
        enabled: bool
        port: int = 7878
        flash: bool = None            # 游戏事件（Mod 扳机流）→ 闪灯，None=不改动

    class ExpMazeReq(BaseModel):
        op: str = "calibrate"

    class ExpDsuReq(BaseModel):
        enabled: bool
        port: int = 26760
        invert: list = None           # [pitch, yaw, roll]，None=不改动

    class ExpDiagReq(BaseModel):
        op: str              # sample / adccalib / autocal
        seconds: float = 5.0
        stage: str = "start"
        on: bool = False

    import protocol
    import devcfg as _devcfg
    import profile as _profile
    import sharecode as _sharecode

    @r.get("/api/exp/profile")
    def exp_profile_read():
        try:
            require_real(engine)
            return {"ok": True, **_profile.SERVICE.read_profile()}
        except Exception as e:
            return err(e)

    @r.post("/api/exp/profile/turbo")
    def exp_profile_turbo(req: ExpTurboReq):
        try:
            require_real(engine)
            return {"ok": True, **_profile.SERVICE.edit(
                lambda b: _profile.set_turbo(b, req.kid, req.mode, req.freq))}
        except Exception as e:
            return err(e)

    @r.post("/api/exp/profile/stick")
    def exp_profile_stick(req: ExpStickReq):
        try:
            require_real(engine)
            return {"ok": True, **_profile.SERVICE.edit(
                lambda b: _profile.set_stick(b, req.side, req.preset, req.center, req.edge,
                                             tuple(req.p1), tuple(req.p2), req.is_round))}
        except Exception as e:
            return err(e)

    @r.post("/api/exp/profile/trigger-curve")
    def exp_profile_trigger(req: ExpTriggerCurveReq):
        try:
            require_real(engine)
            return {"ok": True, **_profile.SERVICE.edit(
                lambda b: _profile.set_trigger_curve(b, req.side, req.zero, req.end))}
        except Exception as e:
            return err(e)

    @r.post("/api/exp/profile/motion")
    def exp_profile_motion(req: ExpMotionReq):
        """体感固件层（与软件层体感互斥——UI 负责，后端两边各自拦 enabled）。"""
        import softmap as _softmap
        try:
            require_real(engine)
            if req.target != _profile.MOTION_OFF and _softmap.HUB.gyro.cfg["enabled"]:
                raise RuntimeError("软件层体感瞄准开着，先关掉再启用固件层（互斥）")
            return {"ok": True, **_profile.SERVICE.edit(
                lambda b: _profile.set_motion(b, req.target, req.enable_key,
                                              req.enable_type, req.dead_zone,
                                              req.sens_x, req.sens_y))}
        except Exception as e:
            return err(e)

    @r.post("/api/exp/profile/gripvib")
    def exp_profile_gripvib(req: ExpGripVibReq):
        try:
            require_real(engine)
            return {"ok": True, **_profile.SERVICE.edit(
                lambda b: _profile.set_grip_vib(b, req.enabled, req.left, req.right))}
        except Exception as e:
            return err(e)

    @r.post("/api/exp/profile/title")
    def exp_profile_title(req: ExpTitleReq):
        try:
            require_real(engine)
            return {"ok": True, **_profile.SERVICE.edit(
                lambda b: _profile.set_title(b, req.title))}
        except Exception as e:
            return err(e)

    @r.get("/api/exp/slots")
    def exp_slots():
        try:
            require_real(engine)
            return {"ok": True, **_profile.SERVICE.read_slots()}
        except Exception as e:
            return err(e)

    @r.post("/api/exp/slots/apply")
    def exp_slots_apply(req: ExpSlotReq):
        try:
            require_real(engine)
            return {"ok": True, **_profile.SERVICE.apply_slot(req.slot)}
        except Exception as e:
            return err(e)

    @r.post("/api/exp/profile/switch")
    def exp_profile_switch(req: ExpSlotReq):
        try:
            require_real(engine)
            return {"ok": True, **_profile.SERVICE.sync_switch(req.slot)}
        except Exception as e:
            return err(e)

    @r.post("/api/exp/factoryreset/slot")
    def exp_factory_slot(req: ExpSlotReq):
        if req.confirm != "RESET":
            return err(ValueError("确认字符串不符（须输入 RESET）"))
        try:
            require_real(engine)
            full_backup(engine)
            return {"ok": True, **_profile.SERVICE.factory_reset_slot(req.slot)}
        except Exception as e:
            return err(e)

    @r.post("/api/exp/factoryreset/all")
    def exp_factory_all(req: ExpSlotReq):
        if req.confirm != "RESET-ALL":
            return err(ValueError("确认字符串不符（须输入 RESET-ALL）"))
        try:
            require_real(engine)
            full_backup(engine)
            return {"ok": True, **_profile.SERVICE.factory_reset_all()}
        except Exception as e:
            return err(e)

    def _extbuild(cmd, payload=b""):
        import extkeys
        return extkeys.build(cmd, payload)

    @r.get("/api/exp/devcfg")
    def exp_devcfg_read():
        try:
            require_real(engine)
            out = {"ok": True, "settings": settings_writer.read(),
                   "nickname": None, "owner": engine.owner,
                   "versions": engine.versions}
            for body in engine.request(_extbuild(2), 2, timeout=0.8, source="devcfg"):
                if body[2] == 2:
                    out["nickname"] = _devcfg.parse_nickname(body)
                    break
            return out
        except Exception as e:
            return err(e)

    @r.post("/api/exp/devcfg/setting")
    def exp_devcfg_setting(req: ExpSettingReq):
        try:
            require_real(engine)
            if req.op == "bit":
                if req.sub is None or not 1 <= req.sub <= 10:
                    raise ValueError("sub 1..10")
                s = settings_writer.write_bit(req.sub, bool(req.on))
            elif req.op == "rate":
                s = settings_writer.write_rate(req.value)
            elif req.op == "precision":
                s = settings_writer.write_precision(req.value)
            elif req.op == "sensitivity":
                s = settings_writer.write_sensitivity(req.value)
            elif req.op == "sleep":
                s = settings_writer.write_sleep(req.value)
            else:
                raise ValueError("op")
            return {"ok": True, "settings": s}
        except Exception as e:
            return err(e)

    @r.post("/api/exp/devcfg/nickname")
    def exp_devcfg_nickname(req: ExpNicknameReq):
        try:
            require_real(engine)
            payload = _devcfg.nickname_packet(req.name)
            engine.send_checked(protocol.build(24, payload), 24, source="devcfg")
            name = None
            for body in engine.request(_extbuild(2), 2, timeout=0.8, source="devcfg"):
                if body[2] == 2:
                    name = _devcfg.parse_nickname(body)
                    break
            return {"ok": True, "nickname": name}
        except Exception as e:
            return err(e)

    @r.post("/api/exp/devcfg/reboot")
    def exp_devcfg_reboot():
        try:
            require_real(engine)
            return settings_writer.reboot()
        except Exception as e:
            return err(e)

    @r.get("/api/exp/owner")
    def exp_owner():
        try:
            require_real(engine)
            o = engine.read_owner()
            if o is None:
                raise RuntimeError("cmd16 无回复")
            return {"ok": True, "owner": o}
        except Exception as e:
            return err(e)

    @r.post("/api/exp/owner/acquire")
    def exp_owner_acquire():
        try:
            require_real(engine)
            return engine.acquire_control()
        except Exception as e:
            return err(e)

    @r.get("/api/exp/gyro")
    def exp_gyro_status():
        import softmap as _softmap
        return {"ok": True, **_softmap.HUB.gyro.status()}

    @r.post("/api/exp/gyro")
    def exp_gyro_config(req: ExpGyroReq):
        import softmap as _softmap
        try:
            # 与固件层互斥：/exp/profile/motion 开固件层时会反向拦软件层；这里开软件层
            # 时固件层状态读档案代价高，由 UI 提示承担（两端文案都有互斥警告）。
            return {"ok": True, **_softmap.HUB.gyro.set_config(dict(req.patch))}
        except Exception as e:
            return err(e)

    @r.get("/api/exp/stickmap")
    def exp_stickmap_status():
        import softmap as _softmap
        return {"ok": True, **_softmap.HUB.stickmap.status()}

    @r.post("/api/exp/stickmap")
    def exp_stickmap_config(req: ExpGyroReq):
        import softmap as _softmap
        try:
            return {"ok": True, **_softmap.HUB.stickmap.set_config(dict(req.patch))}
        except Exception as e:
            return err(e)

    @r.get("/api/exp/rgbbridge")
    def exp_rgb_status():
        return {"ok": True, **rgb.status()}

    @r.post("/api/exp/rgbbridge")
    def exp_rgb_config(req: ExpRgbReq):
        try:
            if req.flash is not None:
                rgb.set_flash(req.flash)
            if req.enabled:
                return {"ok": True, **rgb.start(req.port)}
            return {"ok": True, **rgb.stop()}
        except Exception as e:
            return err(e)

    @r.get("/api/exp/maze")
    def exp_maze_status():
        return {"ok": True, **maze_svc.status()}

    @r.post("/api/exp/maze")
    def exp_maze_op(req: ExpMazeReq):
        try:
            if req.op == "calibrate":
                maze_svc.calibrate()
                return {"ok": True, **maze_svc.status()}
            return err(f"未知操作：{req.op}")
        except Exception as e:
            return err(e)

    @r.get("/api/exp/dsu")
    def exp_dsu_status():
        return {"ok": True, **dsu_svc.status()}

    @r.post("/api/exp/dsu")
    def exp_dsu_config(req: ExpDsuReq):
        try:
            if req.invert is not None:
                if len(req.invert) != 3:
                    return err("invert 需要 [pitch, yaw, roll] 三个布尔值")
                dsu_svc.set_invert(*req.invert)
            if req.enabled:
                dsu_svc.start(req.port)
            else:
                dsu_svc.stop()
            return {"ok": True, **dsu_svc.status()}
        except Exception as e:
            return err(e)

    @r.post("/api/exp/sharecode/encode")
    def exp_share_encode(req: ExpShareReq):
        try:
            if req.kind == "profile":
                require_real(engine)
                import extkeys as _ek
                with _profile.SERVICE._lock:
                    pad = _ek.Pad()
                    st = pad.read_status()
                    blob = _profile.SERVICE._read_live(pad, req.slot if hasattr(req, "slot") else st["active"])
                payload = {"kind": "profile", "slot": st["active"], "blob": bytes(blob).hex()}
            elif req.kind == "blob":
                if not req.blob_hex:
                    raise ValueError("blob_hex 为空")
                payload = {"kind": "profile", "blob": req.blob_hex.replace(" ", "")}
            else:
                raise ValueError(f"未知分享类型: {req.kind}")
            return {"ok": True, "code": _sharecode.encode(payload)}
        except Exception as e:
            return err(e)

    @r.post("/api/exp/sharecode/decode")
    def exp_share_decode(req: ExpShareReq):
        try:
            data = _sharecode.decode(req.code)
            out = {"ok": True, "kind": data.get("kind"), "slot": data.get("slot")}
            if "blob" in data:
                blob = bytes.fromhex(data["blob"])
                if len(blob) != 840:
                    raise ValueError(f"blob 长度异常（{len(blob)}B，应为 840）")
                out["profile"] = _profile.parse_profile(blob)
            return out
        except Exception as e:
            return err(e)

    @r.post("/api/exp/sharecode/apply")
    def exp_share_apply(req: ExpShareReq):
        try:
            require_real(engine)
            data = _sharecode.decode(req.code)
            if data.get("kind") != "profile" or "blob" not in data:
                raise ValueError("只支持档案分享码")
            blob = bytearray(bytes.fromhex(data["blob"]))
            if len(blob) != 840:
                raise ValueError(f"blob 长度异常（{len(blob)}B）")

            def _overwrite(b, src=bytes(blob)):
                b[:] = src
            return {"ok": True, **_profile.SERVICE.edit(_overwrite)}
        except Exception as e:
            return err(e)

    @r.post("/api/exp/diagnostics")
    def exp_diagnostics(req: ExpDiagReq):
        try:
            require_real(engine)
            if req.op == "sample":
                return {"ok": True, **diag_svc.sample(req.seconds)}
            if req.op == "adccalib":
                return {"ok": True, **diag_svc.adc_calib(req.stage)}
            if req.op == "autocal":
                return {"ok": True, **diag_svc.autocal(req.on)}
            raise ValueError("op")
        except Exception as e:
            return err(e)

    @r.get("/api/exp/diagnostics")
    def exp_diagnostics_data():
        return {"ok": True, **diag_svc.sampler.data()}

    return r
