# Mod 管家（ADR-025）：官方飞智 Mod 的下载/安装/生命周期管理。
#
# 官方行为复刻（AdapterTriggerRunner.CheckGame 反编译）：
# - 游戏进程在跑 + 条目启用 + mod 已安装 → 拉起 mod exe（参数 "7878 name=<游戏进程> port=7878"）
# - 游戏退出 → Kill mod 进程
# 我们不装进游戏目录/服务目录，统一装 %APPDATA%\Apex5Unleashed\mods\<gid>\，
# mod 本体只往 127.0.0.1:7878 发包，在哪跑都一样。
# mod 不随软件分发（版权，R2/与封面图同策略），按需从官方 CDN 下载。
import json
import os
import subprocess
import threading
import urllib.request
import zipfile

MODS_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"),
                        "Apex5Unleashed", "mods")
DOWNLOAD_TIMEOUT = 60
MAX_ZIP = 64 * 1024 * 1024          # 官方 mod ~400KB，64MB 上限防异常包


def mods_settings_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Apex5Unleashed", "mods_enabled.json")


class ModManager:
    """生命周期挂前台事件（gameprofiles 的 autoswitch 链路顺带驱动）。"""

    def __init__(self, engine_getter, games, ingress, dsx_port=7878):
        self._engine_getter = engine_getter
        self.games = games                    # GameProfiles
        self.ingress = ingress                # DsxIngress（mod 事件从这进手柄）
        self.dsx_port = dsx_port
        self.proc = None                      # 当前 mod 进程
        self.active_gid = None                # 当前 mod 服务的游戏档案 id
        self.installing = {}                  # gid → 线程（防并发下载）
        self._lock = threading.Lock()
        self.enabled = self._load_enabled()   # {gid: bool}
        self._suppress_count = 0              # 抑制期计数（诊断）

    # ---------- 启用状态持久化 ----------
    def _load_enabled(self):
        try:
            with open(mods_settings_path(), "r", encoding="utf-8") as f:
                return {k: bool(v) for k, v in json.load(f).items()}
        except Exception:
            return {}

    def _save_enabled(self):
        try:
            with open(mods_settings_path(), "w", encoding="utf-8") as f:
                json.dump(self.enabled, f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    # ---------- 安装 ----------
    def mod_dir(self, gid):
        return os.path.join(MODS_DIR, gid)

    def is_installed(self, g):
        m = g.get("mod") or {}
        if not m.get("name"):
            return False
        return os.path.isfile(os.path.join(self.mod_dir(g["id"]), m["name"]))

    def install(self, gid, on_done=None):
        all_ = self.games.all()
        if gid not in all_:
            raise KeyError(gid)
        g = all_[gid]
        m = g.get("mod") or {}
        url = m.get("url")
        if not url or not m.get("name"):
            raise ValueError("该游戏没有可用的 Mod 下载源")
        if m.get("start_type", 1) != 1:
            # 插件型（Fallout4=F4SE / GTA5=ScriptHookV / 怪猎 / RE 系）：官方也是解压进
            # 游戏目录由游戏加载，无独立进程——需要游戏路径且改写游戏文件，v1 不做（ADR-025）
            raise ValueError("该 Mod 为游戏目录插件型，暂不支持自动安装")

        def work():
            err = ""
            try:
                os.makedirs(self.mod_dir(gid), exist_ok=True)
                zpath = os.path.join(MODS_DIR, f"{gid}.zip")
                req = urllib.request.Request(url, headers={"User-Agent": "Apex5Unleashed"})
                with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as r, open(zpath, "wb") as f:
                    total = 0
                    while True:
                        chunk = r.read(65536)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > MAX_ZIP:
                            raise ValueError("下载体积异常，已放弃")
                        f.write(chunk)
                # 解压：zip 内是 mods/<xx>/AdapterTrigger_*.exe 相对路径，展平到 mod_dir
                with zipfile.ZipFile(zpath) as z:
                    for i in z.infolist():
                        if not i.is_file():
                            continue
                        base = i.filename.replace("/", "\\").split("\\")[-1]
                        if not base:
                            continue
                        with z.open(i) as src, \
                                open(os.path.join(self.mod_dir(gid), base), "wb") as dst:
                            dst.write(src.read())
                os.remove(zpath)
                if not self.is_installed(g):
                    raise ValueError("zip 里找不到 " + m["name"])
            except Exception as e:
                err = str(e)
            finally:
                with self._lock:
                    self.installing.pop(gid, None)
            if on_done:
                on_done(err)

        with self._lock:
            if gid in self.installing:
                raise ValueError("正在安装中")
            self.installing[gid] = True
        threading.Thread(target=work, daemon=True, name=f"mod-dl-{gid}").start()

    def uninstall(self, gid):
        self.set_enabled(gid, False)
        import shutil
        if os.path.isdir(self.mod_dir(gid)):
            shutil.rmtree(self.mod_dir(gid), ignore_errors=True)

    # ---------- 启用/停用 ----------
    def set_enabled(self, gid, enabled):
        self.enabled[gid] = bool(enabled)
        self._save_enabled()
        if not enabled and self.active_gid == gid:
            self.stop_mod()
        return self.enabled[gid]

    # ---------- 生命周期（前台事件驱动） ----------
    def _mod_profile(self, exe):
        """前台 exe → 带 mod 字段的档案。不走 games.match()：mod_only 游戏常与
        asb 震动档案同 exe 并存（FH5/2077），match 按 vib 优先会返回 asb 条目，
        mod 就永远拉不起了——这里独立找 mod 档案（vib 适配归 match，两不耽误）。"""
        if not exe:
            return None
        want = exe.lower().removesuffix(".exe")
        for g in self.games.all().values():
            if not g.get("mod"):
                continue
            for e in g["exe"]:
                if e.lower().removesuffix(".exe") == want:
                    return g
        return None

    def on_foreground(self, exe):
        """由 gameprofiles.maybe_autoswitch 发 'foreground' 事件后调用（exe 小写或空）。"""
        g = self._mod_profile(exe)
        want = None
        if g and self.enabled.get(g["id"]) and self.is_installed(g):
            want = g
        if want and self.active_gid == want["id"] and self.proc and self.proc.poll() is None:
            return                              # 已在跑：不动
        self.stop_mod()
        if want:
            self.start_mod(want)

    def start_mod(self, g):
        m = g["mod"]
        exe_path = os.path.join(self.mod_dir(g["id"]), m["name"])
        if not os.path.isfile(exe_path):
            return
        # 官方传给 name= 的是 ProcessGameName（真实游戏进程名）；mod_only 档案的
        # exe[0] 可能是 mod 自己的进程名，不能拿来当游戏名
        game_proc = (m.get("process") or (g.get("exe") or [""])[0]).removesuffix(".exe")
        # XGameMonitor 型：zip 里 game_folder.txt 写死的是打包者的游戏路径，
        # 拉起前改成当前前台游戏所在目录（拿不到全路径就留着——mod 自己会兜底找）
        try:
            import gameprofiles
            fp = gameprofiles.LAST_FOREGROUND_PATH
            gft = os.path.join(self.mod_dir(g["id"]), "game_folder.txt")
            if fp and os.path.isfile(gft):
                game_dir = os.path.dirname(fp)
                cur = open(gft, "r", encoding="utf-8", errors="replace").read().strip()
                if cur.lower() != game_dir.lower():
                    with open(gft, "w", encoding="utf-8") as f:
                        f.write(game_dir)
        except Exception:
            pass
        # 端口用 ingress 实际绑定值（7878 被占时我们落 8787——发给 7878 就进官方服务了）
        port = self.ingress.port or self.dsx_port
        args = f"{port} name={game_proc} port={port}"
        try:    # 官方 GameHelper.StartGameMod 同款参数；CREATE_NO_WINDOW 防 pythonw 黑框
            self.proc = subprocess.Popen(
                [exe_path, args], cwd=os.path.dirname(exe_path),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception as e:
            self._emit_error(f"拉起 {g['name']} 的 Mod 失败: {e}")
            return
        self.active_gid = g["id"]
        self.ingress.clear_ledger()
        # mod 接管扳机期间抑制 grip 震动路由（cmd82 会抢扳机控制权，官方同款互斥）
        eng = self._engine_getter()
        if eng:
            for side in ("left", "right"):
                eng.unbind_grip(side, source="mod:start")
        eng and eng._emit("mod", state="start", game=g["name"],
                          detail=f"{g['name']} 事件级适配已启动（Mod 运行中）")

    def stop_mod(self):
        gid, was = self.active_gid, self.proc is not None
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None
        self.active_gid = None
        if was:
            self.ingress.clear_ledger()
            eng = self._engine_getter()
            if eng:
                for side in ("left", "right"):
                    eng.clear_trigger(side, source="mod:stop")
                g = self.games.match(getattr(self.games, "foreground", None))
                if g and (g.get("vib") or g.get("preset_id")):
                    try:
                        self.games.apply_game(g, eng)   # 回游戏自己的 vib 适配
                    except Exception:
                        pass
                eng._emit("mod", state="stop",
                          detail="事件级适配已停止" + (f"（{gid}）" if gid else ""))

    def _emit_error(self, detail):
        eng = self._engine_getter()
        eng and eng._emit("error", detail=detail)

    # ---------- 状态 ----------
    def status(self):
        all_ = self.games.all()
        out = []
        for gid, g in sorted(all_.items()):
            m = g.get("mod")
            if not m:
                continue
            out.append({"gid": gid, "name": g["name"], "mod_name": m.get("name", ""),
                        "version": m.get("version", ""),
                        "start_type": m.get("start_type", 1),
                        "installed": self.is_installed(g),
                        "enabled": bool(self.enabled.get(gid)),
                        "installing": gid in self.installing,
                        "running": self.active_gid == gid and self.proc
                        and self.proc.poll() is None})
        return {"mods": out, "active_gid": self.active_gid}
