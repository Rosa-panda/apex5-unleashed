# 游戏封面图本地缓存代理（2026-09-20）。
# 痛点：241 款游戏封面是外链（steam akamai / flydigi CDN），pywebview 直连不稳、
# 267 张同时发起常超时 → "很多图刷不出来"。
# 方案：后台线程限流预下载到 %APPDATA%/Apex5Unleashed/imgcache/，前端一律走
# /api/game-img/{gid}（本地命中，秒开）；未就绪 404 no-store，前端退避重试。
import glob
import os
import threading
import time
import urllib.request


def cache_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "Apex5Unleashed", "imgcache")
    os.makedirs(d, exist_ok=True)
    return d


def cached_path(gid):
    """已缓存的封面路径（任意图片后缀），无则 None。"""
    hits = glob.glob(os.path.join(cache_dir(), gid + ".*"))
    return hits[0] if hits else None


def cache_stats():
    """缓存概况：{"count": 文件数, "bytes": 总字节}。"""
    files = glob.glob(os.path.join(cache_dir(), "*.*"))
    return {"count": len(files),
            "bytes": sum(os.path.getsize(f) for f in files if os.path.isfile(f))}


def cache_clear():
    """清空封面缓存，返回释放的字节数。预下载线程下轮会自动重下（网络好才有代价）。"""
    freed = 0
    for f in glob.glob(os.path.join(cache_dir(), "*.*")):
        try:
            freed += os.path.getsize(f)
            os.remove(f)
        except OSError:
            pass
    return freed


# 魔数校验：防 CDN 错误页/半截文件被当图片缓存
_MAGIC = ((b"\x89PNG", ".png"), (b"\xff\xd8", ".jpg"), (b"GIF8", ".gif"))


def _download(gid, url):
    """下载单张 → .part → 魔数校验 → 原子改名。失败清理，返回 False。"""
    tmp = os.path.join(cache_dir(), gid + ".part")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Apex5Unleashed"})
        with urllib.request.urlopen(req, timeout=15) as r, open(tmp, "wb") as f:
            f.write(r.read(2 * 1024 * 1024))          # 封面上限 2MB，够且防炸盘
        with open(tmp, "rb") as f:
            head = f.read(8)
        ext = next((e for m, e in _MAGIC if head.startswith(m)), None)
        if not ext:
            raise ValueError(f"非图片内容: {head[:4]!r}")
        final = os.path.join(cache_dir(), gid + ext)
        os.replace(tmp, final)
        return True
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def start_prefetch(games):
    """daemon 线程：补齐缺失封面；失败 10 分钟后重试；每分钟复查（新导入会补上）。"""
    def loop():
        failed = {}                                    # url → 上次失败时刻
        while True:
            try:
                todo = []
                for g in games.all().values():
                    url = g.get("image")
                    if not url or cached_path(g["id"]):
                        continue
                    if time.time() - failed.get(url, 0) < 600:
                        continue
                    todo.append((g["id"], url))
                for gid, url in todo:                  # 限流：串行 + 间隔，不打爆 CDN
                    if not _download(gid, url):
                        failed[url] = time.time()
                    time.sleep(0.3)
            except Exception:
                pass                                   # 盘/网异常下轮再来
            time.sleep(60)
    threading.Thread(target=loop, daemon=True, name="img-prefetch").start()
