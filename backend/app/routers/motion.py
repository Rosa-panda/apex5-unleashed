# 体感/0xEF 流端点（ADR-029 B8 自 service.py 逐字搬出）：
# 0xEF 手动开关与监听心跳（rawstream 需求登记表）、体感中心总闸（motionmaster 状态机）、
# 模拟器仿真、灯桥闪灯/自测。体感之外的 exp 端点在 routers/explab.py（B7）。
import socket
import time

from fastapi import APIRouter
from pydantic import BaseModel

from .common import err, require_real


def build_motion_router(ctx):
    r = APIRouter()
    engine = ctx.engine
    mm = ctx.mm
    raw = ctx.raw
    dsu_svc = ctx.dsu
    gamesim = ctx.gamesim
    rgb = ctx.rgb

    class ExpImuReq(BaseModel):
        enabled: bool

    class MotionMasterReq(BaseModel):
        enabled: bool

    class ExpSimReq(BaseModel):
        scenario: str = "idle"

    class ExpRgbFlashReq(BaseModel):
        enabled: bool
        rgb: list = [255, 0, 0]

    class ExpRgbTestReq(BaseModel):
        rgb: list = [255, 0, 0]

    @r.post("/api/exp/imu")
    def exp_imu_toggle(req: ExpImuReq):
        """0xEF 运动流手动开关（无 UI，调试用）：走需求登记表 manual 位。"""
        try:
            require_real(engine)
            raw.demands["manual"] = bool(req.enabled)
            on = raw.eval("manual")
            return {"ok": True, "raw": on}
        except Exception as e:
            return err(e)

    @r.post("/api/rawstream")
    def rawstream_heartbeat(req: dict):
        """拓展键监听心跳（ADR-028 修订 2）：前端测试页打开监听时每 15s 打卡，
        padlive 新鲜（<30s）才保持 0xEF 流开——页面关了/断网 30s 内自动收流，
        手柄恢复可休眠。"""
        try:
            raw.heartbeat(bool(req.get("on", True)))
            on = raw.eval("padlive")
            return {"ok": True, "on": bool(req.get("on", True)), "raw": on}
        except Exception as e:
            return err(e)

    # ---- 体感中心总闸端点（状态机在 motionmaster.py）----
    @r.get("/api/motion/master")
    def motion_master_get():
        mm.hits["get"] += 1
        return mm.status()

    @r.post("/api/motion/master")
    def motion_master_set(req: MotionMasterReq):
        import softmap as _softmap
        t0 = time.monotonic()
        mm.hits["post"] += 1
        mm.log(f"POST enabled={req.enabled}")
        note = None
        try:
            if req.enabled:
                try:
                    dsu_svc.start()
                except Exception as e:
                    note = f"DSU 桥启动失败（体感其余功能不受影响）：{e}"
            else:
                # 撤总闸需求：桥+瞄准+体感 UI 推送全关；流是否关由 _raw.eval
                # 按其余消费者（宏录制/拓展键监听）决——没人用即收流，手柄可休眠
                dsu_svc.stop()
                try:
                    _softmap.HUB.gyro.set_config({"enabled": False})
                except Exception:
                    pass
            mm.hub["master"] = bool(req.enabled)
            raw.demands["master"] = bool(req.enabled)
            raw.eval("master-set" if req.enabled else "master-clear")
            mm.save(req.enabled)
            mm.log(f"POST done {req.enabled} in {(time.monotonic() - t0) * 1000:.0f}ms")
            return mm.status(note)
        except Exception as e:
            mm.log(f"POST error {req.enabled}: {e}")
            return err(e)

    @r.get("/api/exp/gamesim")
    def exp_gamesim_status():
        return {"ok": True, **gamesim.status()}

    @r.post("/api/exp/gamesim")
    def exp_gamesim_run(req: ExpSimReq):
        try:
            if req.scenario == "stop":
                gamesim.stop()
                return {"ok": True, **gamesim.status()}
            return {"ok": True, **gamesim.start(req.scenario)}
        except Exception as e:
            return err(e)

    @r.post("/api/exp/rgbbridge/flash")
    def exp_rgb_flash(req: ExpRgbFlashReq):
        try:
            rgb.set_flash(req.enabled, req.rgb)
            return {"ok": True, **rgb.status()}
        except Exception as e:
            return err(e)

    @r.post("/api/exp/rgbbridge/test")
    def exp_rgb_test(req: ExpRgbTestReq):
        """本机往桥发一包颜色，走完整链路（UDP→解析→限频→写灯），让用户直接看到效果。"""
        try:
            if not rgb.enabled:
                raise RuntimeError("桥未启动，先点启动")
            r, g, b = (int(x) for x in req.rgb)
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.sendto(f"{r},{g},{b}".encode("ascii"), ("127.0.0.1", rgb.port))
            finally:
                s.close()
            time.sleep(1.2)          # 越过 1s 限频窗口再看统计
            return {"ok": True, "sent": [r, g, b], **rgb.status()}
        except Exception as e:
            return err(e)

    return r
