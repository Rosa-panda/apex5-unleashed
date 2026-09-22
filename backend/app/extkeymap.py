# 拓展键完整映射（ADR-030，2026-09-22）：官方空间站同款双通道。
# 逆向结论（spacestation decomp：KeyboardMouseInjectRunner / FeizVkeyMouHelper）：
#   手柄目标（视图/菜单/LB/RB/C/Z…）→ 固件键表（0xA3 族，extkeys.ExtKeyMapper，ADR-019）
#   键盘目标 → PC 软件注入。官方走 FeizVKB64.sys 内核驱动；本工具用 SendInput 等价实现。
# 触发源：0xEF 位图（映射前物理按压，engine extkey 事件）——固件透传(255)的键不产生
# 任何标准输出，全靠这里边沿检测后注入，与官方 InjectKeyboardSimulator 同构。
import json
import os
import threading

import extkeys

CFG_NAME = "extkeymap.json"

# 六键默认 = 透传（出厂真值 FACTORY_K5 全 255；ADR-031：拓展键是一等键，不别名
# 已有键位——按 M 键只代表 M 键本身，UI 经 0xEF 流显示，映射仅用户显式配置才生效）
DEFAULTS = {
    name: {"mode": "passthrough"} for name, _kid in extkeys.EXT_KEYS
}
MODES = ("passthrough", "gamepad", "keyboard")


def cfg_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Apex5Unleashed", CFG_NAME)


def load():
    """读持久配置；缺失/损坏回退默认（不抛异常——映射坏了不能连累启动）。"""
    try:
        with open(cfg_path(), "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return {k: dict(v) for k, v in DEFAULTS.items()}
    return sanitize(cfg)


def save(cfg):
    try:
        os.makedirs(os.path.dirname(cfg_path()), exist_ok=True)
        tmp = cfg_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=1)
        os.replace(tmp, cfg_path())
    except OSError:
        pass


def sanitize(cfg):
    """白名单清洗：六键、三模式、target 必须在 TARGET_NAMES、keyboard 必须带 key。"""
    out = {}
    for name, _kid in extkeys.EXT_KEYS:
        c = cfg.get(name) if isinstance(cfg, dict) else None
        if not isinstance(c, dict):
            out[name] = dict(DEFAULTS[name])
            continue
        mode = c.get("mode") if c.get("mode") in MODES else DEFAULTS[name]["mode"]
        item = {"mode": mode}
        if mode == "gamepad":
            tgt = c.get("target", 10)   # 显式选手柄模式但没填目标：兜底 LB（ADR-031 后 DEFAULTS 不含 target）
            item["target"] = tgt if tgt in extkeys.TARGET_NAMES else 10
        elif mode == "keyboard":
            key = str(c.get("key") or "").strip().lower()
            import softmap
            item["key"] = key if key in softmap.VK else "space"
        out[name] = item
    return out


def has_keyboard(cfg):
    return any(c.get("mode") == "keyboard" for c in cfg.values())


def send_kb(name, down):
    """键盘注入单点（模块级函数，测试可 monkeypatch）。"""
    import softmap
    vk = softmap.VK.get(name)
    if vk is not None:
        softmap.key_event(vk, down)


def apply(cfg, raw=None):
    """配置落两条通道：gamepad→固件表目标，其余→透传 255（软件接管防双重触发）。
    keyboard 存在时登记 0xEF 流需求（ADR-028 修订 2），随后保存配置。"""
    cfg = sanitize(cfg)
    targets = {}
    for name, _kid in extkeys.EXT_KEYS:
        c = cfg[name]
        targets[name] = c["target"] if c["mode"] == "gamepad" else 255
    res = extkeys.MAPPER.set_targets(targets)
    if raw is not None:
        raw.demands["extkeymap"] = has_keyboard(cfg)
        try:
            raw.eval("extkeymap")
        except Exception:
            pass
    save(cfg)
    return res


class Runner:
    """engine extkey 事件 → keyboard 模式键的 SendInput 边沿注入。

    事件形态（engine._emit）：位图变化才发，names=当前按下的键名列表。
    边沿检测在此做：与上次按下集合求差集，新进=按下、退出=松开。"""

    def __init__(self, raw=None):
        self.cfg = load()
        self.raw = raw
        self._pressed = set()
        self._lock = threading.Lock()

    def reload(self):
        self.cfg = load()
        with self._lock:
            self._pressed -= {n for n, c in self.cfg.items() if c.get("mode") != "keyboard"}

    def _kb_map(self):
        return {n: c.get("key") for n, c in self.cfg.items()
                if c.get("mode") == "keyboard" and c.get("key")}

    def on_event(self, evt):
        if evt.get("kind") != "extkey":
            return
        names = set(evt.get("names") or [])
        with self._lock:
            kb = self._kb_map()
            pressed = {n for n in names if n in kb}
            for n in pressed - self._pressed:
                send_kb(kb[n], True)
            for n in self._pressed - pressed:
                send_kb(kb[n], False)
            self._pressed = pressed
