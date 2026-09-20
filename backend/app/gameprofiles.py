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


LAST_FOREGROUND_PATH = ""          # 最近一次前台进程全路径（Mod 管家定位游戏目录用）


def foreground_exe():
    """当前前台窗口的进程名（小写 basename），失败返回 None。
    顺带把全路径记到模块级 LAST_FOREGROUND_PATH（XGameMonitor 的 game_folder.txt
    需要游戏安装目录，官方 zip 里写死的是打包者的路径，拉起前要改写）。"""
    global LAST_FOREGROUND_PATH
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
        LAST_FOREGROUND_PATH = buf.value
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
        self._was_online = False              # 设备接入沿：attach 瞬间重放当前适配
        self._active_game = None              # 自动切换当前生效适配的游戏名（None=无）
        self._active_uni = False              # 通用联动是否为自动切换所套（手动设置不算）
        self._cache = ({}, 0.0)               # (档案dict, 加载时刻) —— 档案多了不能每秒全量读盘
        self.subscribers = []                 # 前台变化订阅者（fn(exe)，Mod 管家挂这）
        self._load_settings()

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

    # ---------------- 开关持久化（重启不丢：用户勾过一次就一直算数） ----------------
    @staticmethod
    def _settings_path():
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "Apex5Unleashed", "settings.json")

    def _load_settings(self):
        try:
            with open(self._settings_path(), "r", encoding="utf-8") as f:
                s = json.load(f)
            self.autoswitch = bool(s.get("autoswitch", True))
            self.universal_vib = bool(s.get("universal_vib", False))
        except Exception:
            pass                              # 无文件/坏文件 → 默认值

    def _save_settings(self):
        try:
            with open(self._settings_path(), "w", encoding="utf-8") as f:
                json.dump({"autoswitch": self.autoswitch,
                           "universal_vib": self.universal_vib}, f)
        except Exception:
            pass

    def set_autoswitch(self, enabled):
        self.autoswitch = bool(enabled)
        self._save_settings()
        return self.autoswitch

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
        for k in ("vib", "official", "official_id", "mod_only", "en", "image", "mod"):
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
        self._save_settings()
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
        for k in ("vib", "official", "official_id", "mod_only", "en", "image", "mod"):
            if g.get(k) is not None:
                data[k] = g[k]
        return self.save(data)

    # ---------------- 前台检测自动切换 ----------------
    @staticmethod
    def _norm(exe):
        """匹配规范化：比较时剥 .exe（官方库存进程名不带扩展名）。"""
        return (exe or "").lower().removesuffix(".exe")

    def match(self, exe):
        """exe（小写）→ 命中的游戏档案，无则 None。
        优先级：带适配（vib/preset）的条目 > 用户副本 > 内置。
        2026-09-20 修复：官方导入生成的用户副本（preset 空、无 vib）曾整条遮蔽
        同名内置（内置带 fps-sniper 等），导致 7 款游戏的预设从未自动生效——
        与 RE9 僵尸档案（ADR-022 时期发现）同类病根。"""
        if not exe:
            return None
        want = self._norm(exe)
        hits = [g for g in self.all().values()
                if any(self._norm(e) == want for e in g["exe"])]
        if not hits:
            return None
        adapted = [g for g in hits if g.get("vib") or g.get("preset_id")]
        if len(adapted) == 1:
            return adapted[0]
        if adapted:                              # 多条都带适配：用户优先
            user = [g for g in adapted if not g.get("builtin")]
            return (user or adapted)[0]
        user = [g for g in hits if not g.get("builtin")]
        return (user or hits)[0]

    def maybe_autoswitch(self, engine):
        """由监控线程 1Hz 调用：前台变化时匹配档案并应用（2026-09-20 语义重设计）。
        提示只讲"变化"：进入适配/切换适配/真离开适配，桌面闲逛不发一言。
        设备刚接入（attach 沿）也走一遍：重启后/插线后把当前该生效的适配补上。"""
        exe = foreground_exe()
        just_online = engine.online and not self._was_online
        self._was_online = engine.online
        if exe == self.foreground and not just_online:
            return
        prev_active = self._active_game or self._active_uni   # 之前是否真有适配在生效
        if just_online:
            self._active_game, self._active_uni = None, False  # attach 卫生已清账本
        self.foreground = exe
        engine._emit("foreground", exe=exe or "")
        for fn in self.subscribers:           # Mod 管家等前台驱动组件（不受 autoswitch 开关影响）
            try:
                fn(exe)
            except Exception:
                pass
        if not self.autoswitch:
            return
        g = self.match(exe)
        if g and (g.get("vib") or g.get("preset_id")):
            switched = self._active_game != g["name"]
            self._active_game, self._active_uni = g["name"], False
            try:
                self.apply_game(g, engine)
                if switched:                     # 适配内切窗口/回来不打扰
                    engine._emit("autoswitch", game=g["name"], preset=g.get("preset_id") or "",
                                 detail=f"检测到 {exe}，已应用 {g['name']} 适配")
            except Exception as e:
                engine._emit("error", detail=f"自动应用 {g['name']} 失败: {e}")
        elif self.universal_vib:
            if not self._active_uni:             # 已套着就彻底静默（固件路由全局有效）
                from officialimport import UNIVERSAL_VIB
                for side in ("left", "right"):
                    engine.bind_grip(side, dict(UNIVERSAL_VIB), source="vib:universal")
                engine._emit("autoswitch", game="", preset="",
                             detail="无专属适配，应用通用震动联动")
            self._active_game, self._active_uni = None, True
        else:
            self._active_game, self._active_uni = None, False
            if g:
                # 命中档案但既无 vib 也无预设（如 ASB 清单条目）→ 明确告知，别装看不见
                engine._emit("autoswitch", game=g["name"], preset="",
                             detail=f"{g['name']} 无专属适配参数，标准模式运行")
            elif prev_active and (
                    engine.state["triggers"].get("left") or engine.state["triggers"].get("right")
                    or engine.state["gripBind"].get("left") or engine.state["gripBind"].get("right")):
                # 真·离开适配才发解绑+提示（手动套的效果不由自动切换清）
                for side in ("left", "right"):
                    engine.unbind_grip(side, source="autoswitch:leave")
                engine._emit("autoswitch", game="", preset="", detail="离开游戏，已恢复标准状态")

    def start_watch(self, engine, stop_evt):
        def loop():
            while not stop_evt.is_set():
                try:
                    self.maybe_autoswitch(engine)
                except Exception:
                    pass
                stop_evt.wait(1.0)
        threading.Thread(target=loop, daemon=True, name="fg-watcher").start()
