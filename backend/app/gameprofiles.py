# 游戏档案层（ADR-014）：游戏→exe 匹配→预设；前台检测自动切换（1Hz 轮询 fallback）
# ADR-017：档案可带官方逐游戏 vib 震动联动参数；通用震动联动作为无档案回落；支持自定义 exe。
import ctypes
import json
import os
import threading
import time
from ctypes import wintypes

# ---------------- Windows 前台进程探测（纯 ctypes，无第三方依赖） ----------------
_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32


def foreground_exe():
    """当前前台窗口的进程名（小写 basename），失败返回 None。"""
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = _kernel32.OpenProcess(0x1000, False, pid)     # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(512)
        size = wintypes.DWORD(512)
        if not _kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return None
        return buf.value.split("\\")[-1].lower()
    finally:
        _kernel32.CloseHandle(h)


# ---------------- 档案存储 ----------------
def games_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "Apex5Unleashed", "games")
    os.makedirs(d, exist_ok=True)
    return d


def builtin_games_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "games")


class GameProfiles:
    """游戏档案 = 预设的具名入口 + exe 匹配键。"""

    def __init__(self, preset_store):
        self.presets = preset_store
        self.autoswitch = True
        self.foreground = None                # 当前前台 exe（小写）
        self.universal_vib = False            # 通用震动联动（ADR-017）：无档案前台的回落
        self._cache = ({}, 0.0)               # (档案dict, 加载时刻) —— 档案多了不能每秒全量读盘

    def _load(self, directory, builtin):
        out = {}
        if not os.path.isdir(directory):
            return out
        for fn in sorted(os.listdir(directory)):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(directory, fn), "r", encoding="utf-8") as f:
                    g = json.load(f)
                if isinstance(g.get("name"), str) and isinstance(g.get("exe"), list):
                    g["exe"] = [e.lower() for e in g["exe"]]
                    g["builtin"] = builtin
                    g["id"] = fn[:-5]
                    out[g["id"]] = g
            except Exception:
                continue
        return out

    def list(self):
        return {"builtin": list(self._load(builtin_games_dir(), True).values()),
                "user": list(self._load(games_dir(), False).values()),
                "foreground": self.foreground,
                "autoswitch": self.autoswitch,
                "universal_vib": self.universal_vib}

    def all(self):
        d, ts = self._cache
        now = time.time()
        if d and now - ts < 5.0:              # 5s 缓存：save/delete 后主动失效
            return d
        d = self._load(builtin_games_dir(), True)
        d.update(self._load(games_dir(), False))
        self._cache = (d, now)
        return d

    def _bust(self):
        self._cache = ({}, 0.0)

    def save(self, data):
        from presets import safe_name
        name = (data.get("name") or "").strip()
        if not name or not data.get("exe"):
            raise ValueError("需要游戏名和进程名")
        gid = safe_name(name)
        # 同名内置档案 id 撞车（regen 也用 safe_name 命名）→ 用户副本加后缀，避免 all() 里整条遮蔽内置
        if os.path.isfile(os.path.join(builtin_games_dir(), gid + ".json")):
            gid = gid + "-user"
        g = {"version": 1, "name": name, "note": data.get("note", ""),
             "exe": [e.strip().lower() for e in data["exe"] if e.strip()],
             "preset_id": data.get("preset_id") or "",
             "builtin": False, "id": gid}
        for k in ("vib", "official", "official_id", "mod_only", "en", "image"):
            if data.get(k) is not None:
                g[k] = data[k]
        with open(os.path.join(games_dir(), gid + ".json"), "w", encoding="utf-8") as f:
            json.dump(g, f, ensure_ascii=False, indent=2)
        self._bust()
        return g

    def delete(self, gid):
        all_ = self.all()
        if gid in all_ and all_[gid]["builtin"]:
            raise ValueError("内置档案不可删除")
        p = os.path.join(games_dir(), gid + ".json")
        if not os.path.isfile(p):
            raise KeyError(gid)
        os.remove(p)
        self._bust()

    # ---------------- 应用逻辑（手动套用与自动切换同一条路，ADR-017） ----------------
    def apply_game(self, g, engine):
        """套用一个游戏档案：vib 震动联动（双侧 bind_grip）+ 可选预设。"""
        vib = g.get("vib")
        if vib:
            for side in ("left", "right"):
                engine.bind_grip(side, {k: vib[k] for k in
                                        ("filter", "scale", "stroke", "press", "strength", "freq")},
                                 source=f"game:{g['name']}")
        else:
            for side in ("left", "right"):
                engine.unbind_grip(side, source=f"game:{g['name']}:novib")
        if g.get("preset_id"):
            self.presets.apply(g["preset_id"], engine)

    def set_universal_vib(self, enabled, engine):
        """通用震动联动（ADR-017）：游戏震动→扳机反馈，任何游戏生效（设备端固件路由）。"""
        self.universal_vib = bool(enabled)
        if not engine:
            return self.universal_vib
        if self.universal_vib:
            from officialimport import UNIVERSAL_VIB
            for side in ("left", "right"):
                engine.bind_grip(side, dict(UNIVERSAL_VIB), source="vib:universal")
            # 前台正命中带 vib 的档案时不重复覆盖（参数以档案为准）
            g = self.match(self.foreground)
            if g and g.get("vib"):
                self.apply_game(g, engine)
        else:
            g = self.match(self.foreground)
            if g and g.get("vib"):
                self.apply_game(g, engine)    # 档案自己的 vib 保留
            else:
                for side in ("left", "right"):
                    engine.unbind_grip(side, source="vib:universal:off")
        return self.universal_vib

    def set_exe(self, gid, exe):
        """自定义 exe 定位（特殊版本游戏）：内置档案复制为用户档案后改写匹配键。"""
        all_ = self.all()
        if gid not in all_:
            raise KeyError(gid)
        g = all_[gid]
        names = [e.strip().lower() for e in (exe or []) if e.strip()]
        if not names:
            raise ValueError("exe 列表不能为空")
        data = {"name": g["name"], "exe": names, "note": g.get("note", ""),
                "preset_id": g.get("preset_id") or ""}
        for k in ("vib", "official", "official_id", "mod_only", "en", "image"):
            if g.get(k) is not None:
                data[k] = g[k]
        return self.save(data)

    # ---------------- 前台检测自动切换 ----------------
    @staticmethod
    def _norm(exe):
        """匹配规范化：比较时剥 .exe（官方库存进程名不带扩展名）。"""
        return (exe or "").lower().removesuffix(".exe")

    def match(self, exe):
        """exe（小写）→ 命中的游戏档案，无则 None。用户档案优先于同名内置（自定义/升级副本遮蔽内置）。"""
        if not exe:
            return None
        want = self._norm(exe)
        builtin_hit = None
        for g in self.all().values():
            if any(self._norm(e) == want for e in g["exe"]):
                if not g.get("builtin"):
                    return g
                builtin_hit = builtin_hit or g
        return builtin_hit

    def maybe_autoswitch(self, engine):
        """由监控线程 1Hz 调用：前台变化时匹配档案并应用；无命中回落通用联动/解绑。"""
        exe = foreground_exe()
        if exe == self.foreground:
            return
        self.foreground = exe
        engine._emit("foreground", exe=exe or "")
        if not self.autoswitch:
            return
        g = self.match(exe)
        if g and (g.get("vib") or g.get("preset_id")):
            try:
                self.apply_game(g, engine)
                engine._emit("autoswitch", game=g["name"], preset=g.get("preset_id") or "",
                             detail=f"检测到 {exe}，已应用 {g['name']} 适配")
            except Exception as e:
                engine._emit("error", detail=f"自动应用 {g['name']} 失败: {e}")
        elif self.universal_vib:
            # 无适配档案（或档案无 vib/预设）→ 通用震动联动兜底
            from officialimport import UNIVERSAL_VIB
            for side in ("left", "right"):
                engine.bind_grip(side, dict(UNIVERSAL_VIB), source="vib:universal")
        elif engine.state["triggers"].get("left") or engine.state["triggers"].get("right") \
                or engine.state["gripBind"].get("left") or engine.state["gripBind"].get("right"):
            # 账本非空才发解绑（unbind_grip 含 trigger 清除；普通应用间切换不发命令）
            for side in ("left", "right"):
                engine.unbind_grip(side, source="autoswitch:leave")

    def start_watch(self, engine, stop_evt):
        def loop():
            while not stop_evt.is_set():
                try:
                    self.maybe_autoswitch(engine)
                except Exception:
                    pass
                stop_evt.wait(1.0)
        threading.Thread(target=loop, daemon=True, name="fg-watcher").start()
