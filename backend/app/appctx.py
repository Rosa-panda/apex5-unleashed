# 应用组装上下文（ADR-029 B1 骨架 / B7 收口）。
# main.py 构造的四大件经 create_app 进来；WS 总线、体验区服务群（RgbBridge/
# DsuServer/RawStreamHub…）的实例化与 engine 接线在 build()——按原 create_app
# 行序逐行搬，订阅顺序敏感（bus.publish 先于 RECORDER.on_event；exp 服务群
# 五处 subscribe 接线相对顺序不可换；总闸恢复序列在 MotionMaster 构造内）。
from dataclasses import dataclass, field

import wsbus
import rawstream
import motionmaster


@dataclass
class AppContext:
    engine: object
    store: object
    games: object = None
    mods: object = None
    ingress: object = None
    ui_hooks: object = None

    # 基础设施（build() 构造，routers 经 ctx 访问）
    bus: object = None            # wsbus.WsBus
    mm: object = None             # motionmaster.MotionMaster
    raw: object = None            # rawstream.RawStreamHub

    # 体验区服务群（build() 构造）
    settings_writer: object = field(default=None)
    rgb: object = None
    diag: object = None
    maze: object = None
    dsu: object = None
    gamesim: object = None
    exp_verdicts: object = None
    extkeymap: object = None       # extkeymap.Runner（ADR-030 键盘映射边沿注入）

    def build(self):
        """组装 WS 总线 + 体验区服务群并完成 engine 接线（ADR-029 B7）。

        原 service.create_app 的构造顺序逐字保留：
        subscribe(bus.publish) → subscribe(RECORDER.on_event) → 服务群实例化
        → subscribe_motion(maze/dsu) → RawStreamHub → MotionMaster（构造内完成
        恢复序列 + to_ws 订阅）→ ingress.on_applied → subscribe_motion(softmap/diag)
        → subscribe(softmap.on_key)。"""
        engine = self.engine

        # WS 事件总线（wsbus.py，ADR-029 B1）：订阅顺序敏感——bus.publish 必须先于
        # 宏录制器（0xEF 事件分发达顺序）
        bus = wsbus.WsBus()
        self.bus = bus

        engine.subscribe(bus.publish)
        import macro as _macro
        engine.subscribe(_macro.RECORDER.on_event)   # 宏录制器吃 0xEF 位图事件（ADR-021）

        # ---------- 体验区服务群（ADR-027：全部 15 项软件成品） ----------
        # 真机类操作都走 profile/devcfg（Pad 第二句柄或引擎问答），mock 模式直接 400。
        import devcfg as _devcfg
        import diag as _diag
        import dsu as _dsu
        import gamesim as _gamesim_mod
        import maze as _maze
        import rgbbridge as _rgbbridge
        import softmap as _softmap

        _settings_writer = _devcfg.SettingsWriter(engine)
        self.settings_writer = _settings_writer
        _rgb = _rgbbridge.RgbBridge(engine)
        self.rgb = _rgb
        _diag_svc = _diag.Diagnostics(engine)
        self.diag = _diag_svc
        _maze_svc = _maze.SERVICE
        self.maze = _maze_svc
        _dsu_svc = _dsu.DsuServer(engine)
        self.dsu = _dsu_svc
        _gamesim = _gamesim_mod.GameSim(lambda: self.ingress, lambda: self.rgb)
        self.gamesim = _gamesim
        engine.subscribe_motion(_maze_svc.on_motion)   # 弹珠迷宫的倾斜源（0xEF 运动流）
        engine.subscribe_motion(_dsu_svc.on_motion)    # 模拟器体感桥（DSU/Cemuhook，#18）

        # ---- 0xEF 流按需开关（ADR-028 修订 2）：需求登记表独立模块（rawstream.py），
        # service 只做端点接线，决策/心跳/看门狗全在 RawStreamHub ----
        _raw = rawstream.RawStreamHub(engine)
        self.raw = _raw

        # ---- 体感中心总闸（motionmaster.py，ADR-029 B1 抽出；原 ADR-028）----
        # 构造内完成：持久态恢复（DSU start → _raw.eval）+ 看门狗启动 + motion_to_ws
        # 订阅（30Hz 节流，总闸静默）——原 791-857 行序逐字保留
        _mm = motionmaster.MotionMaster(engine, bus, _dsu_svc, _maze_svc, _softmap.HUB, _raw)
        self.mm = _mm

        if self.ingress:
            self.ingress.on_applied = _rgb.on_game_event    # Mod 扳机事件 → 闪灯联动
        engine.subscribe_motion(_softmap.HUB.on_motion)
        engine.subscribe_motion(_diag_svc.on_motion)
        engine.subscribe(_softmap.HUB.on_key)

        # ---- 拓展键键盘映射（extkeymap.py，ADR-030）：0xEF extkey 事件边沿 → SendInput。
        # keyboard 模式已在配置中时，恢复流需求（watchdog/attach 会按登记表对账开流）----
        import extkeymap as _extkeymap
        _extkm = _extkeymap.Runner(raw=_raw)
        self.extkeymap = _extkm
        engine.subscribe(_extkm.on_event)
        if _extkeymap.has_keyboard(_extkm.cfg):
            _raw.demands["extkeymap"] = True
            try:
                _raw.eval("extkeymap-restore")
            except Exception:
                pass

        # ---------- 体验区判定留痕（ADR-026） ----------
        import explab as _explab
        self.exp_verdicts = _explab.Verdicts()
