# -*- coding: utf-8 -*-
"""DSX ingress + Mod 管家单测（ADR-025）：MockPad 链路验证 cmd51 帧、限频/去重、翻译层。
运行：python -m pytest backend/test_dsx_mod.py -v（或直接 python backend/test_dsx_mod.py）"""
import json
import os
import socket
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))

import dsxingress
import modmgr
import protocol


class FakeEngine:
    """只实现 ingress/modmgr 用到的引擎面。"""
    force_mock = True
    online = True

    def __init__(self):
        self.proxy = {"holder": "self", "detail": "", "since": None}
        self.state = {"triggers": {"left": None, "right": None},
                      "gripBind": {"left": None, "right": None}}
        self.sent = []                     # (cmd, payload, source)
        self.events = []

    def _send(self, frame, source=""):
        # protocol.build：[0]=report [1]5A [2]A5 [3]=cmd [4]=len [5:]=payload
        self.sent.append((frame[3], frame[5:5 + frame[4]], source))

    def _emit(self, kind, **kw):
        self.events.append((kind, kw))

    def bind_grip(self, side, params, source="ui"):
        self.state["gripBind"][side] = source

    def unbind_grip(self, side, source="ui"):
        self.state["gripBind"][side] = None

    def clear_trigger(self, side, source="ui"):
        self.state["triggers"][side] = None


class FakeGames:
    def __init__(self, games):
        self._g = games
        self.foreground = None
        self.subscribers = []

    def all(self):
        return self._g

    def match(self, exe):
        for g in self._g.values():
            if exe and exe in g["exe"]:
                return g
        return None


def make_ingress(eng, port=0):
    ing = dsxingress.DsxIngress(lambda: eng, enabled=True)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", port))
    ing._sock = sock
    ing.port = sock.getsockname()[1]
    return ing


def dsx_pkt(*instructions):
    return json.dumps({"instructions": [
        {"type": 1, "parameters": list(p)} for p in instructions]}).encode("ascii")


class TestIngress(unittest.TestCase):
    def setUp(self):
        self.eng = FakeEngine()
        self.ing = make_ingress(self.eng)
        self.tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def tearDown(self):
        self.ing.stop()
        self.tx.close()

    def test_flydigi_passthrough(self):
        """飞智 mod 成品字节（F1 23 刹车实测包）直通 → cmd51 wire 一致。"""
        self.ing._handle_trigger([0, 1, 19, 2, 30, 1, 0, 150])
        cmd, payload, src = self.eng.sent[-1]
        self.assertEqual(cmd, protocol.CMD_TRIGGER)
        self.assertEqual(payload, bytes([1, 1, 2, 30, 1, 0, 150, 0]))
        self.assertTrue(src.startswith("dsx:"))

    def test_dedup_and_rate_limit(self):
        """同 payload 不重发；不同 payload 在 15ms 窗内丢弃。"""
        self.ing._handle_trigger([0, 2, 19, 2, 100, 1, 5, 20])
        n0 = len(self.eng.sent)
        self.ing._handle_trigger([0, 2, 19, 2, 100, 1, 5, 20])   # 完全相同 → 去重
        self.assertEqual(len(self.eng.sent), n0)
        self.ing._handle_trigger([0, 2, 19, 2, 100, 1, 5, 21])   # 不同但限频窗内
        self.assertEqual(len(self.eng.sent), n0)
        self.ing._last_send[2] = 0.0                              # 过窗 → 放行
        self.ing._handle_trigger([0, 2, 19, 2, 100, 1, 5, 21])
        self.assertEqual(len(self.eng.sent), n0 + 1)

    def test_proxy_hold(self):
        """代理权不在手（空间站占用）→ 只收不发。"""
        self.eng.proxy = {"holder": "external", "detail": "x", "since": None}
        self.ing._handle_trigger([0, 2, 19, 2, 100, 1, 5, 20])
        self.assertEqual(self.eng.sent, [])

    def test_dsx_translation(self):
        """DSX 社区包：Machine 不硬译→ignored；Resistance(3,7) → race 近似；Normal → normal。"""
        self.ing._handle_trigger([0, 1, 18, 1, 2, 3, 4, 5, 6])   # Machine：布局差异大，不译
        self.assertEqual(self.ing.ignored, 1)
        self.ing._last_send[1] = 0.0
        self.ing._handle_trigger([0, 1, 13, 3, 7])
        _, payload, _ = self.eng.sent[-1]
        self.assertEqual(payload[2], 1)                    # wire race
        self.ing._last_send[1] = 0.0                       # 过限频窗
        self.ing._handle_trigger([0, 1, 0])
        _, payload, _ = self.eng.sent[-1]
        self.assertEqual(payload[2], 0)
        self.assertGreater(self.ing.ignored, 0)            # 不认识的 mode 计数

    def test_udp_loop(self):
        """真 UDP 走一遍 _loop：起线程→发包→断言写出→停。"""
        self.ing._stop.clear()
        import threading
        threading.Thread(target=self.ing._loop, daemon=True).start()
        try:
            self.tx.sendto(dsx_pkt([0, 2, 19, 1, 90, 1, 3, 60]), ("127.0.0.1", self.ing.port))
            for _ in range(50):
                if self.eng.sent:
                    break
                time.sleep(0.02)
            self.assertEqual(len(self.eng.sent), 1)
        finally:
            self.ing.stop()


class TestModMgr(unittest.TestCase):
    def setUp(self):
        self.eng = FakeEngine()
        self.ing = make_ingress(self.eng)
        self.games = FakeGames({
            "f1": {"id": "f1", "name": "F1 23", "exe": ["f1_23.exe"],
                   "mod": {"name": "AdapterTrigger_F1Game23.exe", "version": "1",
                           "start_type": 1, "process": "F1_23"}},
            "gta": {"id": "gta", "name": "GTA5", "exe": ["gta5.exe"],
                    "mod": {"name": "ScriptHookV", "start_type": 0}},
        })
        self.mm = modmgr.ModManager(lambda: self.eng, self.games, self.ing)
        # 假装已安装（真 exe 文件，防 start_mod 静默 return）
        d = self.mm.mod_dir("f1")
        os.makedirs(d, exist_ok=True)
        self.exe = os.path.join(d, "AdapterTrigger_F1Game23.exe")
        with open(self.exe, "w") as f:
            f.write("stub")

    def tearDown(self):
        self.mm.stop_mod()
        self.ing.stop()

    def test_plugin_type_rejected(self):
        with self.assertRaises(ValueError):
            self.mm.install("gta")

    def test_lifecycle(self):
        """前台进游戏 → start_mod（Popen 打桩）+ grip 解绑；离开 → stop + 清扳机。"""
        from unittest.mock import patch
        self.mm.set_enabled("f1", True)
        fake_proc = type("P", (), {"poll": lambda self: None, "kill": lambda self: None})()
        with patch.object(modmgr.subprocess, "Popen", return_value=fake_proc) as popen:
            self.mm.on_foreground("f1_23.exe")
            self.assertEqual(self.mm.active_gid, "f1")
            self.assertIs(self.mm.proc, fake_proc)
            # 官方参数格式："<port> name=F1_23 port=<port>"（进程名取 mod.process，
            # 端口取 ingress 实际绑定值——7878 被占时我们落 8787）
            self.assertEqual(popen.call_args[0][0][1],
                             f"{self.ing.port} name=F1_23 port={self.ing.port}")
            # mod 接管期 grip 解绑（抑制 cmd82 抢扳机）
            self.assertIsNone(self.eng.state["gripBind"]["left"])
            # 离开游戏 → mod 杀 + 清扳机 + 状态归位
            self.mm.on_foreground("explorer.exe")
        self.assertIsNone(self.mm.active_gid)
        self.assertIsNone(self.mm.proc)
        self.assertIsNone(self.eng.state["triggers"]["left"])

    def test_disabled_not_started(self):
        self.mm.on_foreground("f1_23.exe")       # 没启用
        self.assertIsNone(self.mm.active_gid)

    def test_status_shape(self):
        st = self.mm.status()
        m = [x for x in st["mods"] if x["gid"] == "f1"][0]
        self.assertTrue(m["installed"])
        self.assertEqual(m["start_type"], 1)


if __name__ == "__main__":
    unittest.main()
