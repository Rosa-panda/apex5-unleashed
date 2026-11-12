# 官方逐游戏适配导入器（ADR-017）：
# 读本机已装飞智空间站的 adapterTriggerGames.json → 转成我们的用户游戏档案（带 vib 震动联动参数）。
# 官方字段 → 我们的档案：
#   ProcessGameName(s)/ExeName → exe 匹配键（补 .exe 变体，前台探测返回带扩展名的小写 basename）
#   IsVibration + VibParams"0,1,1,15,0" + VibFilter + PwmScal → vib {filter,scale,stroke,press,strength,freq}
#   Scenes → note（官方手工调参的手感说明）
#   IsNeedDownMod/ModDownLoadUrl → mod_only（官方深度 Mod，我们不下载不运行，仅震动联动兜底）
# 参数映射依据：ForceTriggerConfigSyncWithGrip(side, bindType, filter, scale, stroke, pressure, strength, freq)
# 与 VibType/VibFilter/PwmScal/VibParams[0..3] 逐位对齐（ADR-017，待真机校准）。
import json
import os

REL_JSON = os.path.join("Configs", "Controller", "Trigger", "adapterTriggerGames.json")
DEFAULT_DIRS = (r"C:\Program Files\Flydigi Space Station",
                r"C:\Program Files (x86)\Flydigi Space Station")
OFFICIAL_JSON = os.path.join(DEFAULT_DIRS[0], REL_JSON)   # 仅作「未找到」时的展示路径

# 通用震动联动默认参数（官方敏感型条目风格：任何游戏震动都能带动扳机）
UNIVERSAL_VIB = {"filter": 1, "scale": 10, "stroke": 0, "press": 1, "strength": 100, "freq": 15}

VIB_KEYS = ("filter", "scale", "stroke", "press", "strength", "freq")


def parse_vib(entry):
    """官方条目 → vib 参数 dict；IsVibration=false 或参数残缺返回 None。"""
    if not entry.get("IsVibration"):
        return None
    try:
        vals = [int(v) for v in str(entry.get("VibParams") or "").split(",")]
        if len(vals) < 4:
            return None
    except ValueError:
        return None
    return {"filter": int(entry.get("VibFilter") or 0),
            "scale": int(entry.get("PwmScal") or 0),
            "stroke": vals[0], "press": vals[1], "strength": vals[2], "freq": vals[3]}


def collect_exes(entry):
    """进程名匹配键：主进程 + 附加进程 + ExeName，含不带扩展名变体（去重、小写）。"""
    names = []
    for k in ("ProcessGameName",):
        if entry.get(k):
            names.append(entry[k])
    for k in ("ProcessGameNames",):
        names.extend(entry.get(k) or [])
    if entry.get("ExeName"):
        names.append(entry["ExeName"])
    out = []
    for n in names:
        n = str(n).strip().lower()
        if not n or n == "none":
            continue
        if n not in out:
            out.append(n)
        stem = n[:-4] if n.endswith(".exe") else n
        if stem and stem not in out:
            out.append(stem)
    return out


def convert_entry(entry):
    """官方条目 → 档案 dict（不含存储字段，由 GameProfiles.save 落盘）。"""
    exes = collect_exes(entry)
    if not exes:
        return None
    vib = parse_vib(entry)
    mod_only = bool(entry.get("IsNeedDownMod") or entry.get("ModDownLoadUrl"))
    parts = []
    if entry.get("Scenes"):
        parts.append(str(entry["Scenes"]).strip())
    if mod_only:
        parts.append("官方深度Mod条目：可在游戏库安装官方 Mod 获得事件级扳机手感（Mod 管家自动拉起）。")
    if entry.get("IsPS5") and not vib:
        parts.append("官方为 PS5/DS 模式条目：本工具无桥接（ADR-020 已删），该条目仅作记录。")
    return {"name": entry.get("GameName") or entry.get("EnGameName") or f"游戏{entry.get('Id')}",
            "exe": exes,
            "note": "\n\n".join(p for p in parts if p),
            "vib": vib,
            "official": True,
            "official_id": entry.get("Id"),
            "mod_only": mod_only}


def _registry_dirs():
    """卸载注册表里飞智空间站的安装目录（issue #3：装在非默认盘时路径不能写死）。
    HKLM 64/32 位视图 + HKCU 都查；缺值/无权限的条目直接跳过。"""
    try:
        import winreg
    except ImportError:
        return []
    sub = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    views = ((winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
             (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
             (winreg.HKEY_CURRENT_USER, 0))
    out = []
    for root, view in views:
        try:
            key = winreg.OpenKey(root, sub, 0, winreg.KEY_READ | view)
        except OSError:
            continue
        with key:
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(key, i)
                except OSError:
                    break
                i += 1
                try:
                    with winreg.OpenKey(key, name, 0, winreg.KEY_READ | view) as k:
                        disp = str(winreg.QueryValueEx(k, "DisplayName")[0]).lower()
                        if "飞智" not in disp and "flydigi" not in disp:
                            continue
                        for val in ("InstallLocation", "DisplayIcon"):
                            try:
                                v = str(winreg.QueryValueEx(k, val)[0]).strip().strip('"')
                            except OSError:
                                continue
                            if val == "DisplayIcon":          # "X:\...\xx.exe",0 → 取目录
                                v = os.path.dirname(v.split(",")[0].strip('"'))
                            if v:
                                out.append(v)
                except OSError:
                    continue
    return out


def _custom_cfg():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Apex5Unleashed", "official_src.json")


def get_custom():
    """用户手动指定的位置（解压版/绿色版空间站注册表里没登记），未设置返回 ""。"""
    try:
        with open(_custom_cfg(), "r", encoding="utf-8") as f:
            return str(json.load(f).get("path") or "")
    except Exception:
        return ""


def resolve(p):
    """手动位置 → 官方库文件：可以是 json 文件本身、空间站根目录、或直接装着 json 的目录。"""
    if not p:
        return None
    if os.path.isfile(p):
        return p
    for c in (os.path.join(p, REL_JSON), os.path.join(p, "adapterTriggerGames.json")):
        if os.path.isfile(c):
            return c
    return None


def set_custom(p):
    """保存手动位置（空 = 清除，恢复自动识别）。位置下找不到官方库直接报错不保存。"""
    p = (p or "").strip().strip('"')
    if not p:
        try:
            os.remove(_custom_cfg())
        except OSError:
            pass
        return None
    r = resolve(p)
    if not r:
        raise FileNotFoundError(f"该位置下没找到 adapterTriggerGames.json：{p}")
    os.makedirs(os.path.dirname(_custom_cfg()), exist_ok=True)
    with open(_custom_cfg(), "w", encoding="utf-8") as f:
        json.dump({"path": p}, f, ensure_ascii=False)
    return r


def official_path():
    """手动位置优先；没设或已失效 → 注册表安装目录 → 默认目录。都没有返回 None。"""
    r = resolve(get_custom())
    if r:
        return r
    seen = set()
    for d in [*_registry_dirs(), *DEFAULT_DIRS]:
        p = os.path.join(d, REL_JSON)
        if p.lower() in seen:
            continue
        seen.add(p.lower())
        if os.path.isfile(p):
            return p
    return None


def import_official(games, path=None):
    """转换官方库 → 用户档案。同名已有档案则**合并升级**（补 vib/说明/进程名，保留自定义 exe）。
    返回 {imported, updated, skipped}。"""
    path = path or official_path()
    if not path:
        raise FileNotFoundError("未找到官方适配库：飞智空间站未安装，或是解压版——请点「库位置」手动选择空间站目录")
    with open(path, "r", encoding="utf-8") as f:
        entries = json.load(f)
    existing = {g["name"]: g for g in games.all().values()}
    imported = updated = skipped = 0
    for entry in entries:
        g = convert_entry(entry)
        if g is None:
            skipped += 1
            continue
        if not g["vib"]:
            # 无震动参数的条目（mod_only / 纯记录）不建副本——壳曾遮蔽内置适配卡
            # （批次⑥）；mod 能力已由 merge_mod_fields 并入内置档案 + Mod 管家接管
            skipped += 1
            continue
        old = existing.get(g["name"])
        if old is None:
            games.save(g)
            imported += 1
        else:
            if old.get("vib") == g["vib"] and old.get("official"):
                continue                       # 已是官方参数，跳过（尊重用户后续微调）
            exes = list(old.get("exe", []))
            for e in g["exe"]:
                if e not in exes:
                    exes.append(e)             # 并集：用户自定义 exe 不丢，官方进程名补全
            games.save({"name": g["name"], "exe": exes,
                        "note": g["note"] or old.get("note", ""),
                        "vib": g["vib"], "official": True,
                        "official_id": g["official_id"], "mod_only": g["mod_only"]})
            updated += 1
    return {"imported": imported, "updated": updated, "skipped": skipped}
