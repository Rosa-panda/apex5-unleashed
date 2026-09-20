# -*- coding: utf-8 -*-
"""ADR-024：ASB 条目 vib 种子参数全自动生成。

数据流：
  官方 vib 条目（34 条，飞智手工调参 = 题材→参数标注数据）
    → Steam storesearch 按英文名补 appid → appdetails 拉 genres（缓存）
  ASB 条目（181 条，带 appid）
    → appdetails 拉 genres（缓存）
  对每条 ASB 条目：与官方条目算题材集交叠，交叠>0 者按交叠数加权平均六参数，
  无交叠回落全体官方均值。clamp 到官方观测值域。
  回写 asb-*.json：+vib +vib_source:"asb-seed" +genres。幂等可重跑。

用法：python tools/update_asb_vib.py [--dry] [--refresh]
  --dry     只统计不写盘
  --refresh 忽略本地 genres 缓存强制重拉
缓存：%APPDATA%/Apex5Unleashed/genre_cache.json（appid → {"genres": [...], "name": ...}）
网络：直连失败自动走 http://127.0.0.1:10808（本机代理）；两次都失败计为拉取失败。
"""
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
GAMES = os.path.join(HERE, "..", "backend", "app", "games")
CACHE_PATH = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"),
                          "Apex5Unleashed", "genre_cache.json")
PROXY = "http://127.0.0.1:10808"
VIB_KEYS = ("filter", "scale", "stroke", "press", "strength", "freq")
UA = {"User-Agent": "Mozilla/5.0 (apex5-unleashed tools/update_asb_vib)"}
_search_cache = {}    # 名称→appid 查询缓存（含 None，防重复打 API）


def http_json(url, timeout=12):
    """直连优先，失败走代理。再失败抛异常。"""
    for proxies in (None, {"http": PROXY, "https": PROXY}):
        try:
            handlers = [urllib.request.ProxyHandler(proxies)] if proxies else []
            opener = urllib.request.build_opener(*handlers)
            req = urllib.request.Request(url, headers=UA)
            with opener.open(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            continue
    raise RuntimeError(f"fetch fail: {url[:80]}")


def load_cache():
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(c):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False)


def search_appid(en_name):
    """英文名 → Steam appid（storesearch 第一个结果，名称需相似）。带缓存。"""
    key = "search:" + en_name.lower()
    if key in _search_cache:
        return _search_cache[key]
    appid = None
    try:
        j = http_json("https://store.steampowered.com/api/storesearch/"
                      f"?term={urllib.request.quote(en_name)}&cc=us&l=en")
        items = j.get("items") or []
        if items:
            appid = items[0]["id"]
    except Exception:
        pass
    _search_cache[key] = appid
    return appid


def fetch_genres(appid, cache, refresh=False):
    """appid → 题材 id 集（英文 id 稳定，不受语言影响）。带缓存。"""
    key = str(appid)
    if not refresh and key in cache:
        return cache[key].get("genres") or []
    try:
        j = http_json(f"https://store.steampowered.com/api/appdetails"
                      f"?appids={key}&filters=genres&l=en")
        d = (j.get(key) or {}).get("data") or {}
        gs = [g["id"] for g in (d.get("genres") or []) if g.get("id")]
        name = d.get("name") or ""
    except Exception:
        gs, name = [], ""
    cache[key] = {"genres": gs, "name": name}
    return gs


def avg_round(vals):
    return int(round(sum(vals) / len(vals))) if vals else 0


def load(fn):
    with open(os.path.join(GAMES, fn), "r", encoding="utf-8") as f:
        return json.load(f)


def dump(fn, g):
    with open(os.path.join(GAMES, fn), "w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False, indent=2)


# ---------------- Pass 0：冗余壳合并 + exe 污染清洗（幂等，2026-09-20 全量体检产物） ----------------
# 背景：早期手作档案（forza-horizon-5 等）与官方空壳（of-call-of-duty 等）无参数无角标，
# 却与 asb 卡撞 exe（match 不确定性）或挡住 asb 卡的中文搜索入口；of-overwatch 官方数据
# 混入了他游戏进程名（horizonforbiddenwest/riftapart），前台误匹配。合并后删壳。
MERGE_INTO_ASB = {
    # 壳文件: (asb目标slug, 追加exe, 中文名覆盖, 补appid)
    "forza-horizon-4.json": ("asb-forzahorizon4", ["forzahorizon4.exe"],
                             "极限竞速：地平线 4", 1293830),
    "forza-horizon-5.json": ("asb-forzahorizon5", [],
                             "极限竞速：地平线 5", None),
    "gta5.json": ("asb-grandtheftautov", ["gta5.exe", "playgtav.exe"],
                  "GTA5 / GTA Online", None),
    "of-call-of-duty.json": ("asb-callofduty",
                             ["cod22-cod.exe", "cod23-cod.exe", "cod24-cod.exe",
                              "sp22-cod.exe", "sp23-cod.exe", "sp24-cod.exe",
                              "cod22-cod", "cod23-cod", "cod24-cod",
                              "sp22-cod", "sp23-cod", "sp24-cod"],
                             "使命召唤", None),
    "of-the-last-of-us-part-ii.json": ("asb-thelastofuspartiiremastered", [],
                                       "最后生还者2", None),
}
DELETE_COVERED = {"sekiro.json"}          # exe 已被 of-sekiro（mod_only 卡）覆盖
CLEAN_EXE_PREFIX = {"of-overwatch.json": {"horizonforbiddenwest", "riftapart"}}
MANUAL_APPID = {"mhw": 582010, "of-gta-5-enhanced": 3240220, "of-overwatch": 2357570}


def merge_pass():
    changed = 0
    for src, (slug, exes, zh, appid) in MERGE_INTO_ASB.items():
        p = os.path.join(GAMES, src)
        if not os.path.isfile(p):
            continue                       # 幂等：壳已删过
        dst_fn = slug + ".json"
        d = load(dst_fn)                   # asb 目标必在（同仓生成物）
        for e in exes:
            if e not in d["exe"]:
                d["exe"].append(e)
        if zh:
            d["name"] = zh
        if appid and not d.get("steam_appid"):
            d["steam_appid"] = appid
        dump(dst_fn, d)
        os.remove(p)
        changed += 1
        print(f"  [合并] {src} → {dst_fn}")
    for fn in DELETE_COVERED:
        p = os.path.join(GAMES, fn)
        if os.path.isfile(p):
            os.remove(p)
            changed += 1
            print(f"  [删壳] {fn}（exe 已被官方 mod_only 卡覆盖）")
    for fn, bad in CLEAN_EXE_PREFIX.items():
        p = os.path.join(GAMES, fn)
        if os.path.isfile(p):
            g = load(fn)
            clean = [e for e in g["exe"]
                     if e.removesuffix(".exe") not in bad]
            if clean != g["exe"]:
                g["exe"] = clean
                dump(fn, g)
                changed += 1
                print(f"  [清污] {fn} 移除他游戏进程名 {sorted(bad)}")
    return changed


# ---------------- Pass 2：非 asb 无参数条目题材种子化（Mod条目语义不动） ----------------
def seed_plain_pass(labeled, bounds, fallback, dry, cache, refresh):
    out = []
    for fn in sorted(os.listdir(GAMES)):
        if not fn.endswith(".json"):
            continue
        g = load(fn)
        if g.get("asb") or g.get("vib") or g.get("mod_only"):
            continue
        appid = g.get("steam_appid") or MANUAL_APPID.get(fn[:-5]) \
            or search_appid(g.get("en") or g.get("name") or "")
        gs = fetch_genres(appid, cache, refresh) if appid else []
        if gs:
            hit = [(len(set(gs) & og), v) for og, v in labeled if len(set(gs) & og) > 0]
            if hit:
                tot = sum(w for w, _ in hit)
                vib = {k: int(round(sum(w * v[k] for w, v in hit) / tot)) for k in VIB_KEYS}
            else:
                vib = dict(fallback)
            gs = sorted(set(gs))
        else:
            vib = dict(fallback)
            gs = None
        for k in VIB_KEYS:
            lo, hi = bounds[k]
            vib[k] = max(lo, min(hi, vib[k]))
        g["vib"] = vib
        g["vib_source"] = "genre-seed"
        if gs:
            g["genres"] = gs
        if appid and not g.get("steam_appid"):
            g["steam_appid"] = appid
        if not dry:
            dump(fn, g)
        out.append(fn[:-5])
        print(f"  [种子] {fn[:-5]}: {vib}")
    return out


def main():
    dry = "--dry" in sys.argv
    refresh = "--refresh" in sys.argv
    files = [fn for fn in os.listdir(GAMES) if fn.endswith(".json")]
    official, asb = [], []
    for fn in sorted(files):
        with open(os.path.join(GAMES, fn), "r", encoding="utf-8") as f:
            g = json.load(f)
        if g.get("vib") and not g.get("asb"):
            g["_fn"] = fn
            official.append(g)
        elif g.get("asb"):
            g["_fn"] = fn
            asb.append(g)
    print(f"官方 vib 条目 {len(official)} · ASB 条目 {len(asb)}")

    cache = load_cache()
    if not dry:
        n = merge_pass()
        if n:
            print(f"合并清洗 {n} 处")
    # ---- 官方条目补 appid + genres（标注数据）----
    labeled = []
    for g in official:
        appid = g.get("steam_appid") or search_appid(g.get("en") or g.get("name") or "")
        if not appid:
            print(f"  [skip] 官方条目无 appid：{g.get('en') or g.get('name')}")
            continue
        gs = fetch_genres(appid, cache, refresh)
        time.sleep(0.3)
        if not gs:
            print(f"  [skip] 官方条目无题材：{g.get('en')} (appid={appid})")
            continue
        labeled.append((set(gs), {k: g["vib"][k] for k in VIB_KEYS}))
        print(f"  [标注] {g.get('en') or g.get('name')}: appid={appid} genres={sorted(gs)}")
    print(f"可用标注条目 {len(labeled)}/{len(official)}")
    if not labeled:
        print("!! 标注数据为空，中止（不写盘）")
        return 1

    # 官方观测值域（clamp 用）+ 全体均值（回落簇）
    bounds = {k: (min(v[k] for _, v in labeled), max(v[k] for _, v in labeled))
              for k in VIB_KEYS}
    fallback = {k: avg_round([v[k] for _, v in labeled]) for k in VIB_KEYS}

    # ---- ASB 条目生成 ----
    ok = miss_genre = 0
    cluster_stat = {}
    for g in asb:
        appid = g.get("steam_appid")
        if not appid:                             # ASB 清单没收录 appid 的，按名补搜
            appid = search_appid(g.get("en") or g.get("name") or "")
            time.sleep(0.3)
        gs = fetch_genres(appid, cache, refresh) if appid else []
        if not gs:
            # 补搜也无果（如原神不在 Steam）：回落簇参数，保证全覆盖
            miss_genre += 1
            print(f"  [缺题材→回落] {g.get('en') or g.get('name')}")
            vib = dict(fallback)
            for k in VIB_KEYS:
                lo, hi = bounds[k]
                vib[k] = max(lo, min(hi, vib[k]))
            g["vib"] = vib
            g["vib_source"] = "asb-seed-fallback"
            cluster_stat["回落"] = cluster_stat.get("回落", 0) + 1
        else:
            time.sleep(0.15)
            gs = set(gs)
            hit = [(len(gs & og), v) for og, v in labeled if len(gs & og) > 0]
            if hit:
                tot = sum(w for w, _ in hit)
                vib = {k: int(round(sum(w * v[k] for w, v in hit) / tot)) for k in VIB_KEYS}
                key = "题材命中"
            else:
                vib = dict(fallback)
                key = "均值回落"
            for k in VIB_KEYS:                   # clamp 到官方值域，不出离谱参数
                lo, hi = bounds[k]
                vib[k] = max(lo, min(hi, vib[k]))
            cluster_stat[key] = cluster_stat.get(key, 0) + 1
            g["vib"] = vib
            g["vib_source"] = "asb-seed"
            g["genres"] = sorted(gs)
        if not dry:
            fn = g.pop("_fn")
            g["note"] = ("原生 DualSense 自适应扳机游戏（ASB/PCGamingWiki 清单）。"
                         "已按题材转为本工具震动联动参数，进游戏自动生效（ADR-024）。")
            with open(os.path.join(GAMES, fn), "w", encoding="utf-8") as f:
                json.dump(g, f, ensure_ascii=False, indent=2)
        ok += 1

    if not dry:
        save_cache(cache)
    print(f"\n生成 {ok}/{len(asb)}（回落 {miss_genre}）· 聚类: {cluster_stat}")

    # ---- 非asb无参数条目（Mod条目除外）题材种子化 ----
    seeded = seed_plain_pass(labeled, bounds, fallback, dry, cache, refresh)
    if seeded:
        print(f"普通条目种子化 {len(seeded)}: {seeded}")
    if not dry:
        save_cache(cache)
    print("值域 clamp:", {k: bounds[k] for k in VIB_KEYS})
    print("回落簇参数:", fallback)
    return 0


if __name__ == "__main__":
    sys.exit(main())
