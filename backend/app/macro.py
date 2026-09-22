# 板载宏（ADR-021，v3.1 宏页方案）：k5 是 proto 3.1，宏存在 163 profile blob 里，
# 不走 172/173/174（那是 v3.2 机型通路，k5 固件的 172 实测只回包 0，openflydigi 同结论）。
# 布局（openflydigi 真机验证 + 本机 2026-09-19 只读复核）：
#   blob[230:768]  宏页：[0]=宏数 1..5（其余值=无宏），[1..6]=每槽偏移（单位 4B，相对页内 6），
#                  每条宏 = 4B 头（触发键 id, 步数 u16 LE, 类型）+ N×4B 步骤（累计时间 u16 LE
#                  单位 10ms tick, 键 id, 事件 0=抬起 1=按下 5=按住），页尾 0xFF 填充
#   blob[820:825]  每槽循环间隔字节（×10ms，0xFF=未设，出厂 3=30ms，上限 2540ms）
#   blob[13+id*3]  键表 target：触发键写 32（宏），固件在 profile 载入时解析宏页——
#                  所以写完必须 162 应用（openflydigi 实测不应用不播放）
# 写通路复用 extkeys 已真机验证的 163 读 → 改 blob → 164/165 写 → 读回 → 162 → 166。
import os
import struct
import threading
import time

import extkeys

OFF_KEY_TABLE = 13
OFF_MACROS = 230
MACRO_REGION = 538
MACRO_HEADER = 6          # count + 5 槽偏移
MACRO_SLOTS = 5
MACRO_WORDS = (MACRO_REGION - MACRO_HEADER) // 4    # 133 词（含每宏 1 词头）
OFF_MACRO_CYCLE = 820
INTERVAL_UNSET = 0xFF
TICK_MS = 10
MAX_MACROS = 5
MAX_STEPS_PER = 64        # 固件 m_fdg_macro_unit_struct_t step[64]
MAX_STEPS_TOTAL = MACRO_WORDS - MACRO_SLOTS         # 128 步全页共享预算
MAX_TICKS = 0xFFFF                                  # 655.35s
MAX_INTERVAL_MS = 2540
TARGET_MACRO = 32
TRIGGER_TYPES = {1: "单次", 2: "按住循环", 3: "点击循环"}
EV_UP, EV_DOWN, EV_HOLD = 0, 1, 5
EXTKEY_NAME = {kid: name for name, kid in extkeys.EXT_KEYS}   # {18:"m1", ..., 23:"rm"}


def backup_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Apex5Unleashed", "macro_backup.bin")


def parse_page(blob):
    """profile blob → {version, macros:[{key_id,type,interval,name,actions}]}。
    interval 取自 820 间隔字节（0xFF → 0）。name 是 v3.2 字段，v3.1 页没有——
    返回空串，前端以触发键为宏的身份。"""
    count = blob[OFF_MACROS]
    macros = []
    if not 1 <= count <= MACRO_SLOTS:
        return {"version": blob[225] | (blob[226] << 8), "macros": []}
    page = blob[OFF_MACROS:OFF_MACROS + MACRO_REGION]
    for s in range(count):
        start = MACRO_HEADER + page[1 + s] * 4
        end = MACRO_HEADER + page[2 + s] * 4 if s + 1 < count else len(page)
        if not MACRO_HEADER <= start <= end <= len(page) or end - start < 4:
            continue
        n = min(page[start + 1] | (page[start + 2] << 8), (end - start - 4) // 4)
        actions = []
        for i in range(n):
            at = start + 4 + i * 4
            actions.append({"t": (page[at] | (page[at + 1] << 8)) * TICK_MS,
                            "key": page[at + 2], "ev": page[at + 3]})
        raw_itv = blob[OFF_MACRO_CYCLE + s]
        macros.append({"key_id": page[start], "type": page[start + 3],
                       "interval": 0 if raw_itv == INTERVAL_UNSET else raw_itv * TICK_MS,
                       "name": "", "actions": actions})
    return {"version": blob[225] | (blob[226] << 8), "macros": macros}


def validate(macros):
    """≤5 条、≤64 步/条、全页 ≤128 步、按下抬起配对、时长 ≤655s、间隔 ≤2540ms。"""
    if len(macros) > MAX_MACROS:
        raise ValueError(f"宏数量超上限（{len(macros)}/{MAX_MACROS}）")
    total = 0
    for m in macros:
        name = m.get("name") or f"键id{m.get('key_id')}"
        acts = m.get("actions") or []
        if not acts:
            raise ValueError(f"宏「{name}」没有动作")
        if len(acts) > MAX_STEPS_PER:
            raise ValueError(f"宏「{name}」动作数超上限（{len(acts)}/{MAX_STEPS_PER}）")
        held = set()
        for a in acts:
            if a["ev"] == EV_DOWN:
                if a["key"] in held:
                    raise ValueError(f"宏「{name}」键 id{a['key']} 重复按下")
                held.add(a["key"])
            elif a["ev"] == EV_UP and a["key"] not in held:
                raise ValueError(f"宏「{name}」键 id{a['key']} 先抬起后按下（必须配对）")
            elif a["ev"] == EV_UP:
                held.discard(a["key"])
        if held:
            raise ValueError(f"宏「{name}」存在未抬起的按下（按下/抬起必须配对）")
        if max(a["t"] for a in acts) > MAX_TICKS * TICK_MS:
            raise ValueError(f"宏「{name}」时长超上限 655s")
        itv = m.get("interval") or 0
        if not 0 <= itv <= MAX_INTERVAL_MS:
            raise ValueError(f"宏「{name}」循环间隔 {itv}ms 超上限 {MAX_INTERVAL_MS}ms")
        total += len(acts)
    if total > MAX_STEPS_TOTAL:
        raise ValueError(f"全部宏合计 {total} 步超页容量 {MAX_STEPS_TOTAL} 步")


def apply_page(blob, macros):
    """把宏页 + 间隔字节写进 blob（就地改）。触发键的键表绑定由调用方一并改。"""
    validate(macros)
    header = bytearray(MACRO_HEADER)
    header[0] = len(macros)
    body = bytearray()
    word = 0
    for s, m in enumerate(macros):
        header[1 + s] = word
        acts = m["actions"]
        body += bytes([m["key_id"] & 0xFF, len(acts) & 0xFF, (len(acts) >> 8) & 0xFF,
                       m["type"] & 0xFF])
        ticks, prev = 0, 0
        for a in acts:
            # 逐段 10ms 量化再累加（对齐官方写入器；先求和再除会漂移）
            ticks = min(MAX_TICKS, ticks + max(0, a["t"] - prev) // TICK_MS)
            body += bytes([ticks & 0xFF, (ticks >> 8) & 0xFF, a["key"] & 0xFF, a["ev"] & 0xFF])
            prev = a["t"]
        word += 1 + len(acts)
    region = bytearray(b"\xff" * MACRO_REGION)
    region[:len(header) + len(body)] = header + body
    blob[OFF_MACROS:OFF_MACROS + MACRO_REGION] = region
    # 间隔属于槽位不属于宏：本条设了才写，腾空的槽回 0xFF（未设）
    for s in range(MACRO_SLOTS):
        itv = macros[s].get("interval") if s < len(macros) else None
        blob[OFF_MACRO_CYCLE + s] = (max(0, min(MAX_INTERVAL_MS, int(itv))) // TICK_MS
                                     if itv else INTERVAL_UNSET)


def macro_bound_ids(blob):
    """当前宏页占用的触发键 id 集合（ADR-032：键表所有权裁决用）。"""
    return {m["key_id"] for m in parse_page(blob)["macros"]}


def resolve_extkey_targets(macros, cfg):
    """六拓展键键表 target 的唯一裁决规则（ADR-032）：宏绑定(32) > 映射配置。
    macros=本次要写的宏列表，cfg=extkeymap 配置。返回 {键名: target}。"""
    bound = {EXTKEY_NAME[m["key_id"]] for m in macros if m["key_id"] in EXTKEY_NAME}
    out = {}
    for name, _kid in extkeys.EXT_KEYS:
        if name in bound:
            out[name] = TARGET_MACRO
            continue
        c = cfg.get(name) or {}
        out[name] = c["target"] if c.get("mode") == "gamepad" and \
            c.get("target") in extkeys.TARGET_NAMES else 255
    return out


def splice_macro_region(cur, bak):
    """宏区作用域拼接（ADR-032）：把备份里的宏页 + 循环间隔 + 六拓展键键表项
    拼进当前 blob（就地改），其余字节保留设备当前值。"""
    cur[OFF_MACROS:OFF_MACROS + MACRO_REGION] = bak[OFF_MACROS:OFF_MACROS + MACRO_REGION]
    cur[OFF_MACRO_CYCLE:OFF_MACRO_CYCLE + MACRO_SLOTS] = \
        bak[OFF_MACRO_CYCLE:OFF_MACRO_CYCLE + MACRO_SLOTS]
    for _name, kid in extkeys.EXT_KEYS:
        at = OFF_KEY_TABLE + kid * 3
        cur[at:at + 3] = bak[at:at + 3]
    return cur


class MacroManager:
    """宏页读写。与键表同一 blob：宏 + 触发键绑定一次提交（164/165 已真机验证）。"""

    def __init__(self):
        self._lock = threading.Lock()

    @staticmethod
    def _pad():
        return extkeys.Pad()

    def _read_blob(self, pad):
        st = pad.read_status()
        blob = bytearray(pad.read_config(st["active"]))
        pad.apply(st["active"])
        return st["active"], blob

    def read(self, cfg=None):
        with self._lock:
            pad = self._pad()
            if cfg is None:
                cfg = pad.read_status()["active"]
            blob = bytearray(pad.read_config(cfg))
            pad.apply(cfg)
        return {"cfg": cfg, "size": len(blob), **parse_page(blob)}

    def write(self, macros, unbind=()):
        """读当前 blob → 备份 → 写宏页 + 六键键表（ADR-032 单一所有权：宏 32 >
        映射配置）→ 校验/应用/保存。unbind 参数已废弃（保留兼容）：删除宏 =
        列表少一条，被腾出的键由裁决规则自动回落映射配置。被宏占用的键的映射
        配置同时归位 passthrough，防配置与设备脱节。"""
        import extkeymap
        with self._lock:
            pad = self._pad()
            st = pad.read_status()
            cfg = st["active"]
            blob = bytearray(pad.read_config(cfg))
            try:
                with open(backup_path(), "wb") as f:
                    f.write(bytes(blob))
            except OSError:
                pass
            apply_page(blob, macros)
            map_cfg = extkeymap.load()
            targets = resolve_extkey_targets(macros, map_cfg)
            kid_of = dict(extkeys.EXT_KEYS)        # name -> kid
            for name, tgt in targets.items():
                kid = kid_of[name]
                blob[OFF_KEY_TABLE + kid * 3] = tgt & 0xFF
            for name in [n for n, t in targets.items() if t == TARGET_MACRO]:
                if map_cfg.get(name, {}).get("mode") != "passthrough":
                    map_cfg[name] = {"mode": "passthrough"}   # 宏占用键的配置归位
            extkeymap.save(map_cfg)
            blob[225:227] = struct.pack("<H", ((blob[226] << 8) | blob[225]) + 1)
            ver, warnings = self._commit_checked(pad, blob, cfg)
        return {"ok": True, "cfg": cfg, "version": ver, "warnings": warnings,
                "targets": targets}

    def _commit_checked(self, pad, blob, cfg):
        """164/165 → 读回 → 162 → 166（语义同 extkeys._commit，宏页一并落盘）。"""
        ver = (blob[226] << 8) | blob[225]
        packs = [blob[i:i + extkeys.PKG] for i in range(0, len(blob), extkeys.PKG)]
        if not any(b[2] == extkeys.CMD_WRITE_START for b in
                   pad.exchange(extkeys.build(extkeys.CMD_WRITE_START,
                                              bytes([cfg, 0, len(packs), extkeys.PKG])))):
            raise RuntimeError("164 写-开始无 ACK")
        for i, p in enumerate(packs):
            if not any(b[2] == extkeys.CMD_WRITE_PACK for b in
                       pad.exchange(extkeys.build(extkeys.CMD_WRITE_PACK, bytes([i]) + p))):
                raise RuntimeError(f"165 包 {i} 无 ACK")
        back = pad.read_config(cfg)
        if bytes(back) != bytes(blob):
            raise RuntimeError("写后读回不一致")
        if not pad.apply(cfg):
            raise RuntimeError("162 应用无 ACK")
        time.sleep(0.4)
        warnings = []
        if not any(b[2] == extkeys.CMD_SAVE for b in
                   pad.exchange(extkeys.build(extkeys.CMD_SAVE, struct.pack("<H", ver)), wait=1.5)):
            warnings.append("166 保存无 ACK：本次上电内已生效，重启手柄可能丢失")
        extkeys.enable_raw_stream(pad)   # 0xEF 位图流保险（真机曾见配置写入后开关被冲掉）
        return ver, warnings

    def backup(self):
        with self._lock:
            pad = self._pad()
            cfg, blob = self._read_blob(pad)
        path = backup_path()
        with open(path, "wb") as f:
            f.write(bytes(blob))
        return {"path": path, "macros": len(parse_page(blob)["macros"])}

    def restore(self):
        """恢复备份：只拼回宏区作用域（宏页+间隔+六拓展键键表项，ADR-032），
        不再全量回写配置槽——映射/调参等其他字节保留设备当前值。"""
        with self._lock:
            with open(backup_path(), "rb") as f:
                bak = f.read()
            if len(bak) != 840:
                raise RuntimeError(f"备份文件不合法（{len(bak)}B，应为 840B 全量 profile）")
            pad = self._pad()
            cfg = pad.read_status()["active"]
            cur = bytearray(pad.read_config(cfg))
            blob = splice_macro_region(cur, bak)
            blob[225:227] = struct.pack("<H", ((blob[226] << 8) | blob[225]) + 1)
            ver, warnings = self._commit_checked(pad, blob, cfg)
        return {"ok": True, "cfg": cfg, "version": ver, "warnings": warnings}


class Recorder:
    """0xEF 位图录制器：engine 总线喂位图变化 → 动作序列。
    拓展键 18-23 不录（是触发键位，不进动作）；65s 自动封笔；停录时仍按住的键自动补抬起。"""

    def __init__(self):
        self._lock = threading.Lock()
        self.active = False
        self._t0 = 0.0
        self._prev = frozenset()
        self._actions = []

    def on_event(self, evt):
        if evt.get("kind") != "extkey":
            return
        try:
            bits = int(evt.get("bits") or "0", 16)
        except ValueError:
            return
        self.feed(bits)

    def feed(self, bits):
        with self._lock:
            if not self.active:
                return
            cur = frozenset(i for i in range(32) if bits >> i & 1 and i not in EXTKEY_NAME)
            t = min(int((time.monotonic() - self._t0) * 1000), MAX_TICKS * TICK_MS)
            for k in sorted(cur - self._prev):
                self._actions.append({"t": t, "key": k, "ev": EV_DOWN})
            for k in sorted(self._prev - cur):
                self._actions.append({"t": t, "key": k, "ev": EV_UP})
            self._prev = cur
            if t >= MAX_TICKS * TICK_MS:
                self.active = False

    def start(self):
        with self._lock:
            self.active = True
            self._t0 = time.monotonic()
            self._prev = frozenset()
            self._actions = []

    def stop(self):
        with self._lock:
            if not self.active:
                return {"actions": [], "seconds": 0.0}
            self.active = False
            t = min(int((time.monotonic() - self._t0) * 1000), MAX_TICKS * TICK_MS)
            for k in sorted(self._prev):
                self._actions.append({"t": t, "key": k, "ev": EV_UP})
            self._prev = frozenset()
            return {"actions": list(self._actions), "seconds": round(t / 1000, 2)}

    def status(self):
        with self._lock:
            sec = (time.monotonic() - self._t0) if self.active else 0.0
            return {"recording": self.active, "steps": len(self._actions),
                    "seconds": round(min(sec * 1000, MAX_TICKS * TICK_MS) / 1000, 2)}


MANAGER = MacroManager()
RECORDER = Recorder()
