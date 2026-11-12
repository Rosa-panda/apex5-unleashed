# 游戏档案层（ADR-014）：游戏→exe 匹配→震动联动/Mod；前台检测自动切换（1Hz 轮询 fallback）
# 2026-11：去掉游戏绑预设；同一游戏多条档案运行时合并为一张卡（_merge）。
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
    """游戏档案 = exe 匹配键 + 震动联动参数（vib）+ 可选官方 Mod。一游戏一卡（见 _merge）。"""

    def __init__(self, preset_store):
        self.presets = preset_store
        self.autoswitch = True
        self.foreground = None                # 当前前台 exe（小写）
        self.universal_vib = False            # 通用震动联动（ADR-017）：无档案前台的回落
        self.vibfix_auto = False              # 震动修复自动出手（默认关：自动出手要弹系统授权框，打扰且曾疑似拖垮启动；
                                              # 默认只在界面明显提示 + 一键修复，用户自己决定）
        self._vibfix_user_set = False         # 用户是否显式选择过（只有显式选择才落盘）
        self.feedback = True                  # 适配生效时手柄短震一下（全屏游戏里看不到界面提示，靠手感确认）
        self._blip_at = {}                    # 提示键 → 上次震动时刻（防抖）
        self._was_online = False              # 设备接入沿：attach 瞬间重放当前适配
        self._active_game = None              # 自动切换当前生效适配的游戏名（None=无）
        self._active_uni = False              # 通用联动是否为自动切换所套（手动设置不算）
        self._cache = ({}, 0.0)               # (合并后档案dict, 加载时刻) —— 档案多了不能每秒全量读盘
        self.subscribers = []                 # 前台变化订阅者（fn(exe)，Mod 管家挂这）
        self.mod_running = lambda: None       # main 注入：Mod 管家正在服务的档案 id（无则 None）
        self.disabled = set()                 # 用户手动禁用的适配档案 id（issue #2）
        self._dirty = False                   # 禁用/启用后强制重评一次前台适配
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
        # 游戏库页每 3s 轮询本端点：与 all() 同享 5s TTL（save/delete 走 _bust 主动失效）。
        # ⚠ TTL 内重复调用返回同一批 dict 对象（调用方只许序列化，勿原地修改）。
        d = self.all()
        return {"builtin": [g for g in d.values() if g["builtin"]],
                "user": [g for g in d.values() if not g["builtin"]],
                "foreground": self.foreground,
                "autoswitch": self.autoswitch,
                "universal_vib": self.universal_vib,
                "vibfix_auto": self.vibfix_auto,
                "feedback": self.feedback,
                "disabled": sorted(self.disabled),
                "active": self.active_info()}

    def active_info(self):
        """当前真正生效的适配：{gid, source, origin}。source ∈ mod / vib / universal；
        origin = vib 参数来源（official 官方调参 / guess 推算 / custom 自定义）。"""
        gid = self.mod_running()
        if gid:
            return {"gid": gid, "source": "mod", "origin": ""}
        if self.autoswitch:
            g = self.match(self.foreground)
            if g and g.get("dsx"):
                return {"gid": g["id"], "source": "dsx", "origin": ""}
            if g and g.get("vib"):
                return {"gid": g["id"], "source": "vib", "origin": g.get("vib_origin") or ""}
        if self._active_uni:
            return {"gid": None, "source": "universal", "origin": ""}
        return None

    def set_disabled(self, gid, disabled):
        """手动禁用/启用某条适配：禁用后自动切换与 Mod 管家都不再选它。"""
        if gid not in self.all():
            raise KeyError(gid)
        if disabled:
            self.disabled.add(gid)
        else:
            self.disabled.discard(gid)
        self._save_settings()
        self._dirty = True
        return bool(disabled)

    def all(self):
        d, ts = self._cache
        now = time.time()
        if d and now - ts < 5.0:              # 5s 缓存：save/delete 后主动失效
            return d
        d = self._load(builtin_games_dir(), True)
        d.update(self._load(games_dir(), False))
        d = self._merge(d)
        self._cache = (d, now)
        return d

    def _bust(self):
        self._cache = ({}, 0.0)

    @classmethod
    def _keys(cls, g):
        """匹配键：exe 去扩展名，剔除 Mod 程序自己的进程名（xgamemonitor/forzadualsense
        等曾被官方 ExeName 带进来，导致几十款无关游戏被串成「同一个游戏」）。"""
        m = g.get("mod") or {}
        skip = {cls._norm(m.get("mod_process")), cls._norm(m.get("name"))} - {""}
        return [k for k in dict.fromkeys(cls._norm(e) for e in g.get("exe") or [])
                if k and k not in skip]

    @classmethod
    def _merge(cls, raw):
        """一游戏一卡（2026-11 issue #2）：进程名有交集的档案合并成一条。
        - 卡片本体（id/名称/来源）取：带 Mod 的 > 内置 > 官方——Mod 安装目录/启用状态按 id 存，不能变；
        - 震动参数取：用户档案（自定义/导入，多份时后保存的优先） > 官方调参 > 推算；
        - 进程名取并集；没有进程名的条目照样显示成卡片（前台检测匹配不上，用户点卡上的
          「选择 exe」指定后才生效）。用户指定 exe 存成的用户档案与它同名，按名字并回同一张卡。
        被并掉的条目 id 记在 merged，用户档案 id 记在 user_id（卡片「删除自定义」用）。"""
        items = []
        keyless = []
        for g in raw.values():
            keys = cls._keys(g)
            if keys:
                items.append((g, set(keys)))
            else:
                keyless.append(g)
        groups = []                                   # [(成员列表, 键集合)]
        for g, keys in items:
            hit = [grp for grp in groups if grp[1] & keys]
            members, allkeys = [g], set(keys)
            for grp in hit:
                members += grp[0]
                allkeys |= grp[1]
                groups.remove(grp)
            groups.append((members, allkeys))
        for g in keyless:
            name = g["name"].strip().lower()
            same = next((grp for grp in groups
                         if any(x["name"].strip().lower() == name for x in grp[0])), None)
            if same:
                same[0].append(g)
            else:
                groups.append(([g], set()))
        out = {}
        for members, _ in groups:
            members.sort(key=lambda g: -g.get("saved_at", 0))   # 用户档案后保存的在前，内置保持原序
            base = sorted(members, key=lambda g: (not g.get("mod"), not g["builtin"],
                                                  not g.get("official")))[0]
            vm = sorted((g for g in members if g.get("vib")),
                        key=lambda g: (g["builtin"], bool(g.get("vib_source")), not g.get("official")))
            vm = vm[0] if vm else None
            m = dict(base)
            m["exe"] = list(dict.fromkeys(e for g in members for e in g["exe"]
                                          if cls._norm(e) in set(cls._keys(g))))
            fm = next((g for g in members if g.get("feel")), None)   # 用户档案在前：用户的手感配置优先
            if fm:
                m["feel"] = fm["feel"]
            m["vib"] = vm["vib"] if vm else None
            m["vib_source"] = vm.get("vib_source") if vm else None
            m["vib_origin"] = (None if not vm else
                               "custom" if not vm["builtin"] and not vm.get("official") else
                               "guess" if vm.get("vib_source") else "official")
            m["origin"] = ("demo" if base.get("dsx") else       # 内置演示游戏（游戏直连扳机）
                           "official" if base.get("official") else
                           "ds" if base["builtin"] else "custom")   # 内置非官方 = 推算参数
            users = [g["id"] for g in members if not g["builtin"]]
            m["user_id"] = users[0] if users else None
            m["merged"] = [g["id"] for g in members if g is not base]
            out[m["id"]] = m
        return out

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
            self.feedback = bool(s.get("feedback", True))
            # 旧键 vibfix_auto 一律不认：它连「没动过的默认值」也落盘，分不清是不是用户的选择。
            # 新键 vibfix_auto_user 只在用户于设置里显式切换后才写入。
            if "vibfix_auto_user" in s:
                self.vibfix_auto = bool(s["vibfix_auto_user"])
                self._vibfix_user_set = True
            self.disabled = set(s.get("disabled_games") or [])
        except Exception:
            pass                              # 无文件/坏文件 → 默认值

    def _save_settings(self):
        try:
            d = {"autoswitch": self.autoswitch,
                 "universal_vib": self.universal_vib,
                 "feedback": self.feedback,
                 "disabled_games": sorted(self.disabled)}
            if self._vibfix_user_set:             # 只记用户的显式选择，默认值不落盘
                d["vibfix_auto_user"] = self.vibfix_auto
            with open(self._settings_path(), "w", encoding="utf-8") as f:
                json.dump(d, f)
        except Exception:
            pass

    def set_autoswitch(self, enabled):
        self.autoswitch = bool(enabled)
        self._save_settings()
        return self.autoswitch

    def set_feedback(self, enabled):
        self.feedback = bool(enabled)
        self._save_settings()
        return self.feedback

    def blip(self, engine, key):
        """适配生效 / 离开 / Mod 启动时，手柄短震一下作确认（全屏游戏里看不到工具界面）。
        同一个 key 20 秒内只震一次：切窗口出去又马上回来不连震。"""
        if not self.feedback:
            return
        t = time.time()
        if t - self._blip_at.get(key, 0.0) < 20.0:
            return
        self._blip_at[key] = t
        try:
            engine.set_rumble(200, 200, duration=0.18, source="autoswitch:feedback")
        except Exception:
            pass

    def set_vibfix_auto(self, enabled):
        self.vibfix_auto = bool(enabled)
        self._vibfix_user_set = True
        self._save_settings()
        return self.vibfix_auto

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
             "saved_at": time.time(),            # 多份自定义撞同一游戏时：后保存的优先
             "builtin": False, "id": gid}
        for k in ("vib", "official", "official_id", "mod_only", "en", "image", "mod", "feel"):
            if data.get(k) is not None:
                g[k] = data[k]
        with open(os.path.join(games_dir(), gid + ".json"), "w", encoding="utf-8") as f:
            json.dump(g, f, ensure_ascii=False, indent=2)
        self._bust()
        return g

    # ---------------- 自定义配置导入 / 导出（别人写好的方案可分享、导入） ----------------
    VIB_KEYS = ("filter", "scale", "stroke", "press", "strength", "freq")

    def import_config(self, data):
        """导入一个或一组游戏配置（JSON 对象或数组），存为用户档案。格式见 README。
        与已有游戏进程名重叠 → 自动并入那张卡，震动参数以导入的为准。"""
        items = data if isinstance(data, list) else [data]
        if not items:
            raise ValueError("配置为空")
        parsed = []
        for it in items:
            if not isinstance(it, dict):
                raise ValueError("配置格式不对：每条应是一个 JSON 对象")
            name = str(it.get("name") or "").strip()
            exe = it.get("exe")
            exe = [exe] if isinstance(exe, str) else exe
            if not name or not isinstance(exe, list) or not any(str(e).strip() for e in exe):
                raise ValueError(f"「{name or '?'}」缺少 name 或 exe（游戏进程名）")
            g = {"name": name, "exe": [str(e) for e in exe], "note": str(it.get("note") or "")}
            if it.get("en"):
                g["en"] = str(it["en"])
            vib = it.get("vib")
            if vib is not None:
                try:
                    g["vib"] = {k: max(0, min(255, int(vib[k]))) for k in self.VIB_KEYS}
                except Exception:
                    raise ValueError(f"「{name}」的 vib 需要 {'/'.join(self.VIB_KEYS)} 六个整数")
            mod = it.get("mod")
            if isinstance(mod, dict) and mod.get("name"):
                g["mod"] = {k: mod[k] for k in ("name", "url", "version", "start_type",
                                                "process", "mod_process") if k in mod}
            feel = it.get("feel")
            if feel is not None:
                # 游戏自己读取的手感配置（结构由游戏定义，工具原样保存、导出）
                if not isinstance(feel, dict):
                    raise ValueError(f"「{name}」的 feel 应是一个 JSON 对象")
                if len(json.dumps(feel, ensure_ascii=False)) > 200_000:
                    raise ValueError(f"「{name}」的 feel 过大（上限约 200KB）")
                g["feel"] = feel
            if not g.get("vib") and not g.get("mod") and not g.get("feel"):
                raise ValueError(f"「{name}」至少要有 vib（震动参数）、mod 或 feel（手感配置）之一")
            parsed.append(g)
        return [self.save(g) for g in parsed]       # 先全部校验再落盘，坏一条不留半截

    def export_config(self, gid):
        """导出一张卡的配置（可直接再导入/分享给别人）。"""
        g = self.all().get(gid)
        if not g:
            raise KeyError(gid)
        out = {"format": "apex5-game/2", "name": g["name"], "exe": g["exe"]}
        for k in ("en", "note"):
            if g.get(k):
                out[k] = g[k]
        if g.get("genres"):
            # Steam 题材编号 → 名称（推算参数就是按这些题材估的；不认识的保留原编号）
            names = {"1": "动作", "2": "策略", "3": "角色扮演", "4": "休闲", "9": "竞速", "18": "体育",
                     "23": "独立", "25": "冒险", "28": "模拟", "29": "大型多人在线", "37": "免费开玩",
                     "70": "抢先体验", "71": "暴力", "73": "血腥"}
            out["题材"] = [names.get(str(x), str(x)) for x in g["genres"]]
        origin = {"official": "官方空间站", "ds": "DS推算", "demo": "内置演示", "custom": "自定义"}
        out["来源"] = {"卡片": origin.get(g.get("origin"), ""),
                     "震动参数": {"official": "官方调参", "guess": "按题材推算", "custom": "自定义"}.get(
                         g.get("vib_origin") or "", "")}
        for k in ("vib", "mod", "feel"):
            if g.get(k):
                out[k] = g[k]
        doc = {"格式": "改完直接在游戏库「导入配置」导回；只需保留想改的字段，name 和 exe 必须有。"}
        if g.get("vib"):
            doc["vib"] = ("震动联动：让手柄固件把游戏的震动转成扳机反馈。filter 滤波 / scale 缩放 / stroke 行程 / "
                          "press 触发点 / strength 力度 / freq 频率，均为 0-255 整数；"
                          "官方游戏的数值来自飞智空间站，推算游戏的数值按题材估算，可按手感自行微调。")
        if g.get("feel"):
            doc["feel"] = ("游戏自己读取的手感配置，结构由游戏定义，工具原样保存。"
                           "改完导入后在游戏里按 F5 重新读取；只写想改的部分，缺的自动用默认值。"
                           "扳机参数是固件原始量程 1-255；形如 [低频, 高频, 秒] 的震动三元组强度为 0-1。")
        if g.get("mod"):
            doc["mod"] = "官方事件级 Mod：name 为程序文件名，url 为下载地址（可省略，手动放进 Mod 文件夹也行）。"
        out["_doc"] = doc
        return out

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
        """套用一个游戏档案：vib 震动联动（双侧 bind_grip）。"""
        vib = g.get("vib")
        if vib:
            for side in ("left", "right"):
                engine.bind_grip(side, {k: vib[k] for k in
                                        ("filter", "scale", "stroke", "press", "strength", "freq")},
                                 source=f"game:{g['name']}")
        else:
            for side in ("left", "right"):
                engine.unbind_grip(side, source=f"game:{g['name']}:novib")

    def set_universal_vib(self, enabled, engine):
        """通用震动联动（ADR-017）：游戏震动→扳机反馈，任何游戏生效（设备端固件路由）。"""
        self.universal_vib = bool(enabled)
        self._save_settings()
        if not engine:
            return self.universal_vib
        if self.mod_running():
            return self.universal_vib          # Mod 接管扳机期间不绑 grip（停 mod 时会按档案回放）
        fg = self.match(self.foreground)
        if fg and fg.get("dsx"):
            return self.universal_vib          # 前台是游戏直连驱动扳机：同理不绑 grip
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
        """自定义 exe 定位（特殊版本游戏）：给这张卡追加进程名。
        追加到该游戏的用户档案（没有就新建一条只含进程名的），进程名与原卡有交集 →
        _merge 仍合成同一张卡，参数/Mod 照旧，不再复制出第二张卡。"""
        all_ = self.all()
        if gid not in all_:
            raise KeyError(gid)
        g = all_[gid]
        names = [e.strip().lower() for e in (exe or []) if e.strip()]
        if not names:
            raise ValueError("exe 列表不能为空")
        uid = g.get("user_id")
        p = os.path.join(games_dir(), f"{uid}.json") if uid else ""
        if uid and os.path.isfile(p):
            with open(p, "r", encoding="utf-8") as f:
                u = json.load(f)
            u["exe"] = list(dict.fromkeys([*(u.get("exe") or []), *names]))
            with open(p, "w", encoding="utf-8") as f:
                json.dump(u, f, ensure_ascii=False, indent=2)
            self._bust()
            return u
        return self.save({"name": g["name"], "exe": [*g["exe"], *names]})

    # ---------------- 前台检测自动切换 ----------------
    @staticmethod
    def _norm(exe):
        """匹配规范化：比较时剥 .exe（官方库存进程名不带扩展名）。"""
        return (exe or "").lower().removesuffix(".exe")

    def match(self, exe):
        """exe（小写）→ 命中的游戏档案，无则 None。
        档案已按进程名合并（_merge，一游戏一卡），正常只会命中一条；
        万一多条（进程名不重叠却同名 exe 变体）：带适配（vib/mod）> 用户 > 内置。"""
        if not exe:
            return None
        want = self._norm(exe)
        hits = [g for g in self.all().values()
                if g["id"] not in self.disabled
                and any(self._norm(e) == want for e in g["exe"])]
        if not hits:
            return None
        adapted = [g for g in hits if g.get("vib") or g.get("mod") or g.get("dsx")]
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
        if exe == self.foreground and not just_online and not self._dirty:
            return
        self._dirty = False
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
        if self.mod_running():
            # Mod 已由上面的订阅者拉起并解绑 grip（cmd82 接管扳机）。这里再套 vib/
            # 通用联动会把 grip 绑回去，和 Mod 抢扳机（issue #2）；停 mod 时 stop_mod 会回放档案
            self._active_game, self._active_uni = None, False
            return
        g = self.match(exe)
        if g and g.get("dsx"):
            # 游戏自己经 DSX 入口实时驱动扳机（内置演示游戏）：不绑震动联动——否则固件
            # 会把游戏震动也路由到扳机，和游戏发来的扳机指令打架
            if self._active_game != g["name"]:
                for side in ("left", "right"):
                    engine.unbind_grip(side, source=f"game:{g['name']}:dsx")
                engine._emit("autoswitch", game=g["name"], preset="",
                             detail=f"检测到 {exe}，由游戏直连驱动扳机")
                self.blip(engine, g["name"])
            self._active_game, self._active_uni = g["name"], False
        elif g and g.get("vib"):
            switched = self._active_game != g["name"]
            self._active_game, self._active_uni = g["name"], False
            try:
                self.apply_game(g, engine)
                if switched:                     # 适配内切窗口/回来不打扰
                    engine._emit("autoswitch", game=g["name"], preset="",
                                 detail=f"检测到 {exe}，已应用 {g['name']} 适配")
                    self.blip(engine, g["name"])
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
                # 命中档案但没有震动参数（如只有 Mod、Mod 未启用）→ 明确告知，别装看不见
                engine._emit("autoswitch", game=g["name"], preset="",
                             detail=f"{g['name']} 无专属适配参数，标准模式运行")
            elif prev_active and (
                    engine.state["triggers"].get("left") or engine.state["triggers"].get("right")
                    or engine.state["gripBind"].get("left") or engine.state["gripBind"].get("right")):
                # 真·离开适配才发解绑+提示（手动套的效果不由自动切换清）
                for side in ("left", "right"):
                    engine.unbind_grip(side, source="autoswitch:leave")
                engine._emit("autoswitch", game="", preset="", detail="离开游戏，已恢复标准状态")
                self.blip(engine, "__leave__")

    def start_watch(self, engine, stop_evt):
        def loop():
            while not stop_evt.is_set():
                try:
                    self.maybe_autoswitch(engine)
                except Exception:
                    pass
                stop_evt.wait(1.0)
        threading.Thread(target=loop, daemon=True, name="fg-watcher").start()
