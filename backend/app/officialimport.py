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

OFFICIAL_JSON = r"C:\Program Files\Flydigi Space Station\Configs\Controller\Trigger\adapterTriggerGames.json"

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


def official_path():
    return OFFICIAL_JSON if os.path.isfile(OFFICIAL_JSON) else None


def import_official(games, path=None):
    """转换官方库 → 用户档案。同名已有档案则**合并升级**（补 vib/说明/进程名，保留用户 preset_id 与自定义 exe）。
    返回 {imported, updated, skipped}。"""
    path = path or official_path()
    if not path:
        raise FileNotFoundError("未找到官方适配库（飞智空间站未安装或版本不同）")
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
            games.save({**g, "preset_id": ""})
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
                        "preset_id": old.get("preset_id") or "",
                        "vib": g["vib"], "official": True,
                        "official_id": g["official_id"], "mod_only": g["mod_only"]})
            updated += 1
    return {"imported": imported, "updated": updated, "skipped": skipped}
