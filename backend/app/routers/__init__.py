# routers 包（ADR-029 B2）：按域拆分的 APIRouter，service.create_app include。
# 纪律：工厂闭包注入（build_xxx_router(ctx)），函数内延迟 import 保持原位不提升。
from . import system as _system
from . import ws as _ws
from . import control as _control
from . import led as _led

build_system_router = _system.build_system_router
build_ws_router = _ws.build_ws_router
build_control_router = _control.build_control_router
build_led_router = _led.build_led_router
