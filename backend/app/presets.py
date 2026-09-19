# 预设库：内置包预设 + 用户预设（%APPDATA%\Apex5Unleashed\presets），事务式应用
import json
import os
import time

PRESET_VERSION = 1


def user_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "Apex5Unleashed", "presets")
    os.makedirs(d, exist_ok=True)
    return d


def builtin_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "presets")


class PresetStore:
    def __init__(self):
        self.builtin = self._load(builtin_dir(), builtin=True)
        self.user = {}

    def _load(self, directory, builtin):
        out = {}
        if not os.path.isdir(directory):
            return out
        for fn in sorted(os.listdir(directory)):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(directory, fn), "r", encoding="utf-8") as f:
                    p = json.load(f)
                if isinstance(p.get("name"), str) and isinstance(p.get("actions"), list):
                    p["builtin"] = builtin
                    p["id"] = fn[:-5]
                    out[p["id"]] = p
            except Exception:
                continue
        return out

    def reload_user(self):
        self.user = self._load(user_dir(), builtin=False)

    def list(self):
        self.reload_user()
        return {"builtin": list(self.builtin.values()), "user": list(self.user.values())}

    def get(self, pid):
        self.reload_user()
        return self.builtin.get(pid) or self.user.get(pid)

    def save(self, data):
        """data: {name, note?, actions:[...]}。同名覆盖。"""
        name = (data.get("name") or "").strip()
        if not name:
            raise ValueError("名称不能为空")
        pid = safe_name(name)
        p = {"version": PRESET_VERSION, "name": name, "note": data.get("note", ""),
             "actions": data.get("actions", []), "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
             "builtin": False, "id": pid}
        path = os.path.join(user_dir(), pid + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False, indent=2)
        return p

    def delete(self, pid):
        self.reload_user()
        if pid in self.builtin:
            raise ValueError("内置预设不可删除")
        if pid not in self.user:
            raise KeyError(pid)
        os.remove(os.path.join(user_dir(), pid + ".json"))

    def apply(self, pid, engine):
        """事务式应用（TECH-SPEC §4）：清空→逐条应用→失败回滚到 panic 基线。"""
        p = self.get(pid)
        if p is None:
            raise KeyError(pid)
        snapshot = json.loads(json.dumps(engine.state["triggers"]))
        applied = []
        try:
            for a in p.get("actions", []):
                kind = a.get("kind")
                if kind == "trigger":
                    engine.set_trigger(a["side"], a["mode"], a.get("params", {}),
                                        preview=False, source=f"preset:{p['name']}")
                    applied.append(("trigger", a["side"]))
                elif kind == "rumble":
                    engine.set_rumble(a.get("l", 0), a.get("r", 0),
                                      duration=a.get("duration"), source=f"preset:{p['name']}")
                elif kind == "grip":
                    engine.bind_grip(a["side"], a.get("params", {}), source=f"preset:{p['name']}")
                    applied.append(("grip", a["side"]))
                else:
                    raise ValueError(f"未知动作类型 {kind}")
        except Exception:
            engine.panic(source=f"preset:{p['name']}:rollback")
            raise
        return {"applied": len(p.get("actions", [])), "name": p["name"]}


def safe_name(s):
    """预设 id 仅用 ASCII（要进 URL/文件名），中文等折叠为空 + 短哈希防碰撞。"""
    import hashlib
    keep = [c if (c.isascii() and (c.isalnum() or c in "-_")) else "" for c in s]
    stem = "".join(keep).strip() or "preset"
    digest = hashlib.sha1(s.encode("utf-8")).hexdigest()[:6]
    return f"{stem}-{digest}"
