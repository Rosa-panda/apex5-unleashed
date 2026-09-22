# 应用组装上下文（ADR-029 B1 骨架）。
# main.py 构造的四大件经 create_app 进来；体验区服务群（RgbBridge/DsuServer/
# RawStreamHub…）的实例化与 engine 接线在 B7 收进 build()——按现行行序逐行搬，
# 订阅顺序敏感（bus.publish 先于 RECORDER.on_event；总闸恢复序列不可换）。
from dataclasses import dataclass, field


@dataclass
class AppContext:
    engine: object
    store: object
    games: object = None
    mods: object = None
    ingress: object = None
    ui_hooks: object = None

    # B1 起：基础设施（service.py 构造后挂上来，routers 经 ctx 访问）
    bus: object = None            # wsbus.WsBus
    mm: object = None             # motionmaster.MotionMaster
    raw: object = None            # rawstream.RawStreamHub

    # B7 起：体验区服务群（build() 构造）
    settings_writer: object = field(default=None)
    rgb: object = None
    diag: object = None
    maze: object = None
    dsu: object = None
    gamesim: object = None
    exp_verdicts: object = None
