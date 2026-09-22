# REST + WS 服务层（TECH-SPEC §6）。挂前端静态资源的单进程入口由 main.py 组装。
# ADR-029 B7 起：服务群组装收进 appctx.AppContext.build()，端点按域住进 routers/，
# 本文件只剩组装（中间件 + include + 收尾的体感端点，B8 后仅剩骨架）。
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import appctx
import routers


def create_app(engine, store, games=None, ui_hooks=None, mods=None, ingress=None):
    app = FastAPI(title="Apex5 Unleashed", docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    ctx = appctx.AppContext(engine=engine, store=store, games=games,
                            mods=mods, ingress=ingress, ui_hooks=ui_hooks)
    # 组装 WS 总线 + 体验区服务群 + engine 订阅接线（行序敏感，见 AppContext.build）
    ctx.build()

    # ---------- API 响应头：no-store ----------
    # FastAPI JSONResponse 不带缓存头，WebView2 会启发式缓存 GET——轮询永远读到
    # 死状态（开关「分不出开没开」的帮凶）。API 一律禁缓存；静态资源（带 hash）不受影响。
    @app.middleware("http")
    async def _api_no_store(request, call_next):
        resp = await call_next(request)
        if request.url.path.startswith("/api"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    app.on_event("startup")(ctx.bus.grab_loop)

    # ---------- 系统/WS（ADR-029 B2 起 routers 化）----------
    app.include_router(routers.build_system_router(ctx))
    app.include_router(routers.build_ws_router(ctx))

    # ---------- 控制/灯光（ADR-029 B3 起 routers 化）----------
    app.include_router(routers.build_control_router(ctx))
    app.include_router(routers.build_led_router(ctx))
    # ---------- 屏幕/拓展键/宏（ADR-029 B4 起 routers 化）----------
    app.include_router(routers.build_screen_router(ctx))
    app.include_router(routers.build_extkeys_router(ctx))
    app.include_router(routers.build_macro_router(ctx))

    # ---------- 预设/游戏（ADR-029 B5 起 routers 化）----------
    app.include_router(routers.build_presets_router(ctx))
    app.include_router(routers.build_games_router(ctx))

    # ---------- 设置域：震动修复/Mod 管家/开机自启（ADR-029 B6 起 routers 化）----------
    app.include_router(routers.build_settings_router(ctx))

    # ---------- 测试台/体验区/体感（ADR-029 B7-B8 起 routers 化）----------
    app.include_router(routers.build_testbench_router(ctx))
    app.include_router(routers.build_explab_router(ctx))
    app.include_router(routers.build_motion_router(ctx))

    # imgcache/game-img 已随 B5 归入 routers/games.py
    # ---------- 事件流 ----------
    # /ws 已在 B2 随 routers/ws.py 挂载（bus.attach）

    return app
