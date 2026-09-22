# routers 包（ADR-029 B2）：按域拆分的 APIRouter，service.create_app include。
# 纪律：工厂闭包注入（build_xxx_router(ctx)），函数内延迟 import 保持原位不提升。
from . import system as _system
from . import ws as _ws
from . import control as _control
from . import led as _led
from . import screen as _screen
from . import extkeys as _extkeys
from . import macro as _macro
from . import presets as _presets
from . import games as _games
from . import settings as _settings

build_system_router = _system.build_system_router
build_ws_router = _ws.build_ws_router
build_control_router = _control.build_control_router
build_led_router = _led.build_led_router
build_screen_router = _screen.build_screen_router
build_extkeys_router = _extkeys.build_extkeys_router
build_macro_router = _macro.build_macro_router
build_presets_router = _presets.build_presets_router
build_games_router = _games.build_games_router
build_settings_router = _settings.build_settings_router
