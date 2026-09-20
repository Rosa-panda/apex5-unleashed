# -*- coding: utf-8 -*-
"""ADR-022(修订 ADR-024 批次)：导入 ApexSenseBridge DS 原生游戏清单为内置档案。

去重规则（2026-09-20 修正）：
  官方条目**真带适配参数（vib 或 preset_id）**才跳过 ASB 同名条目（官方实测参数优先）；
  mod_only 空壳官方条目（无 vib 无 preset，官方靠游戏内 Mod 做事件级）不再挡 ASB——
  此前地平线5 等热门游戏被空壳挡住，库里无参数可套（用户实测发现的真 bug）。
已有 asb-*.json（含已生成的 vib）一律保留不覆盖。

用法：python tools/update_asb_list.py [--dry]
数据源：github.com/ReynArts/ApexSenseBridge data/supported_games.json（直连失败走 10808 代理）
"""
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
GAMES = os.path.join(HERE, "..", "backend", "app", "games")
RAW_URLS = [
    "https://raw.githubusercontent.com/ReynArts/ApexSenseBridge/main/data/supported_games.json",
    "https://raw.githubusercontent.com/ReynArts/ApexSenseBridge/master/data/supported_games.json",
]
PROXY = "http://127.0.0.1:10808"
UA = {"User-Agent": "Mozilla/5.0 (apex5-unleashed tools/update_asb_list)"}


def fetch():
    last = None
    for url in RAW_URLS:
        for proxies in (None, {"http": PROXY, "https": PROXY}):
            try:
                handlers = [urllib.request.ProxyHandler(proxies)] if proxies else []
                opener = urllib.request.build_opener(*handlers)
                req = urllib.request.Request(url, headers=UA)
                with opener.open(req, timeout=20) as r:
                    return json.loads(r.read().decode("utf-8"))
            except Exception as e:
                last = e
    raise RuntimeError(f"数据源拉取失败: {last}")


def norm(s):
    """规范化名：小写、只留字母数字（CJK 名归一成空串→不参与匹配，防误撞）。"""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def main():
    dry = "--dry" in sys.argv
    data = fetch()
    games = [g for g in data.get("games", [])
             if g.get("adaptiveTriggers") or g.get("hapticFeedback")]
    print(f"ASB 清单 {len(games)}/{data.get('totalGames')} 条（updatedAt {data.get('updatedAt', '')[:10]}）")

    # 官方真适配条目的封锁集：规范化 en 名 + exe 名
    block_names, block_exe = set(), set()
    for fn in os.listdir(GAMES):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(GAMES, fn), "r", encoding="utf-8") as f:
            g = json.load(f)
        if g.get("asb") or not (g.get("vib") or g.get("preset_id")):
            continue                      # asb 自己 / 官方空壳（mod_only 等）→ 不挡
        for k in (g.get("en"), g.get("name")):
            n = norm(k)
            if n:
                block_names.add(n)
        for e in g.get("exe") or []:
            n = norm(e)
            if n:
                block_exe.add(n)

    # 已有 asb 档案集（slug + appid）：保留不覆盖
    have_asb_slug, have_asb_appid = set(), set()
    for fn in os.listdir(GAMES):
        if fn.startswith("asb-") and fn.endswith(".json"):
            have_asb_slug.add(fn[4:-5])
            with open(os.path.join(GAMES, fn), "r", encoding="utf-8") as f:
                j = json.load(f)
            if j.get("steam_appid"):
                have_asb_appid.add(str(j["steam_appid"]))

    added = blocked = exist = 0
    for g in games:
        title = g.get("title") or ""
        slug = g.get("normalized") or norm(title)
        if not slug:
            continue
        appid = g.get("steamAppId")
        if str(appid) in have_asb_appid or slug in have_asb_slug:
            exist += 1
            continue
        exes = [e.lower() for e in (g.get("executables") or g.get("exe")
                                    or g.get("discordExecutables") or []) if e]
        n_title = norm(title)
        n_en = norm(g.get("en") or "")
        if (n_title in block_names or n_en in block_names
                or any(norm(e) in block_exe for e in exes)):
            blocked += 1                  # 官方真适配条目在同名覆盖 → 官方优先
            continue
        out = {"version": 1, "name": title, "en": title,
               "exe": exes,
               "note": "原生 DualSense 自适应扳机游戏（ASB/PCGamingWiki 清单）。",
               "image": g.get("iconUrl") or "",
               "asb": True, "source": "asb-list"}
        if appid:
            out["steam_appid"] = appid
        if not dry:
            with open(os.path.join(GAMES, f"asb-{slug}.json"), "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=2)
        added += 1
        print(f"  [+]{title} (exe={len(exes)}, appid={appid})")
    print(f"\n新增 {added} · 官方真适配挡下 {blocked} · 已在库 {exist}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
