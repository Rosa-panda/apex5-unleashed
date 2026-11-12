//! 手感层：扳机（DSX UDP → Apex5 Unleashed → 手柄）与震动（XInput 双马达）的出口。
//!
//! 扳机链路：游戏把自己当成一个「Mod」，往工具的 DSX 入口（127.0.0.1:7878，被占时 8787）
//! 发飞智扩展格式的 JSON：`{"instructions":[{"type":1,"parameters":[0,侧,19,模式,p1..p5]}]}`，
//! 工具原样转成手柄扳机指令。工具没开时这些包没人收，游戏照常能玩（只是没有扳机效果）。
//!
//! 手感数值不在这里写死，见 `tune.rs`（档案里的 `feel` 配置，可导出 / 导入 / F5 热重载）。
use std::net::UdpSocket;

pub const L: usize = 0;
pub const R: usize = 1;

/// 工具入口每侧 15ms 内的包会被直接丢弃，所以同侧两次发送至少隔这么久
const MIN_GAP: f64 = 0.03;
/// 状态没变也定期重发：工具中途重启 / 偶发丢包后能自己恢复（工具侧对重复包去重，无副作用）
const KEEPALIVE: f64 = 0.5;

/// 一侧扳机的目标状态：飞智 wire 模式号 + 5 个参数字节
#[derive(Clone, Copy, PartialEq, Debug)]
pub struct Trig {
    pub mode: u8,
    pub p: [u8; 5],
}

fn b(v: f32) -> u8 {
    v.round().clamp(1.0, 255.0) as u8
}

impl Trig {
    /// 松弛：没有任何阻力
    pub const NORMAL: Trig = Trig { mode: 0, p: [0; 5] };

    /// 阻尼：从 stroke 位置起出现阻力，resistance 越大越硬
    pub fn race(stroke: f32, resistance: f32) -> Trig {
        Trig { mode: 1, p: [b(stroke), b(resistance), 1, 0, 0] }
    }
    /// 后坐：扣过触发点后回弹冲击
    pub fn recoil(stroke: f32, press: f32, strength: f32, freq: f32) -> Trig {
        Trig { mode: 2, p: [b(stroke), b(press), b(strength), b(freq), 1] }
    }
    /// 二段：stroke 处有一道坎，压过去后回弹 recoil_stroke
    pub fn sniper(stroke: f32, recoil_stroke: f32, strength: f32) -> Trig {
        Trig { mode: 3, p: [b(stroke), b(recoil_stroke), b(strength), 1, 0] }
    }
    /// 锁死：在 stroke 位置顶住，扣不下去
    pub fn lock(stroke: f32, strength: f32) -> Trig {
        Trig { mode: 4, p: [b(stroke), b(strength), 1, 0, 0] }
    }
    /// 震动：扳机自身以 freq 频率抖动
    pub fn vibration(stroke: f32, press: f32, strength: f32, freq: f32) -> Trig {
        Trig { mode: 5, p: [b(stroke), b(press), b(strength), b(freq), 1] }
    }

    pub fn name(&self, cn: bool) -> &'static str {
        match (self.mode, cn) {
            (0, true) => "松弛",
            (1, true) => "阻尼",
            (2, true) => "后坐",
            (3, true) => "二段",
            (4, true) => "锁死",
            (5, true) => "震动",
            (0, false) => "NORMAL",
            (1, false) => "RACE",
            (2, false) => "RECOIL",
            (3, false) => "SNIPER",
            (4, false) => "LOCK",
            (5, false) => "VIBRATION",
            _ => "?",
        }
    }

    /// 调试面板用：把参数按字段名展开
    pub fn params(&self) -> String {
        let p = self.p;
        match self.mode {
            1 => format!("stroke={} resistance={}", p[0], p[1]),
            2 | 5 => format!("stroke={} press={} strength={} freq={}", p[0], p[1], p[2], p[3]),
            3 => format!("stroke={} recoil_stroke={} strength={}", p[0], p[1], p[2]),
            4 => format!("stroke={} strength={}", p[0], p[1]),
            _ => String::new(),
        }
    }

    /// 设置里的「扳机强度」：只缩放每个模式里代表力度的那一个字段
    fn scaled(self, k: f32) -> Trig {
        if k >= 0.999 {
            return self;
        }
        let i = match self.mode {
            1 | 4 => 1,
            2 | 3 | 5 => 2,
            _ => return self,
        };
        let mut t = self;
        t.p[i] = b(t.p[i] as f32 * k);
        t
    }
}

/// DSX 发送端：每侧一个「基础状态」（由当前武器/背包决定）+ 一个限时「冲击覆盖」（受伤、爆炸、击发）
pub struct Dsx {
    sock: Option<UdpSocket>,
    pub port: u16,
    /// 端口是否来自工具写的端口文件（否则是默认 7878）
    pub port_found: bool,
    base: [Trig; 2],
    over: [Option<(Trig, f32)>; 2],
    sent: [Option<Trig>; 2],
    sent_t: [f64; 2],
    rescan_t: f64,
    pub enabled: bool,
    pub scale: f32,
    pub packets: u32,
}

fn discover_port() -> Option<u16> {
    let mut dirs = Vec::new();
    if let Ok(t) = std::env::var("TEMP") {
        dirs.push(t);
    }
    dirs.push("C:\\Temp".to_string());
    for d in dirs {
        let p = std::path::Path::new(&d).join("DualSenseX").join("DualSenseX_PortNumber.txt");
        if let Ok(s) = std::fs::read_to_string(p) {
            if let Ok(port) = s.trim().parse::<u16>() {
                if port != 0 {
                    return Some(port);
                }
            }
        }
    }
    None
}

impl Dsx {
    pub fn new() -> Dsx {
        let sock = UdpSocket::bind("127.0.0.1:0").ok();
        if let Some(s) = &sock {
            let _ = s.set_nonblocking(true);
        }
        let found = discover_port();
        Dsx {
            sock,
            port: found.unwrap_or(7878),
            port_found: found.is_some(),
            base: [Trig::NORMAL; 2],
            over: [None; 2],
            sent: [None; 2],
            sent_t: [0.0; 2],
            rescan_t: 0.0,
            enabled: true,
            scale: 1.0,
            packets: 0,
        }
    }

    /// 设定一侧的基础状态（每帧调用都行，内部只在变化时发包）
    pub fn set(&mut self, side: usize, t: Trig) {
        self.base[side] = t;
    }

    /// 限时冲击：dur 秒内盖过基础状态，到期自动回落
    pub fn kick(&mut self, side: usize, t: Trig, dur: f32) {
        self.over[side] = Some((t, dur));
    }

    pub fn kick_both(&mut self, t: Trig, dur: f32) {
        self.kick(L, t, dur);
        self.kick(R, t, dur);
    }

    /// 两侧回到松弛并取消冲击（进菜单 / 暂停时用）
    pub fn relax(&mut self) {
        self.base = [Trig::NORMAL; 2];
    }

    /// 此刻实际希望手柄呈现的状态（已计入冲击覆盖、强度缩放、总开关）
    pub fn effective(&self, side: usize) -> Trig {
        if !self.enabled || self.scale <= 0.01 {
            return Trig::NORMAL;
        }
        let t = match self.over[side] {
            Some((t, _)) => t,
            None => self.base[side],
        };
        t.scaled(self.scale)
    }

    pub fn update(&mut self, dt: f32, now: f64) {
        if now - self.rescan_t > 2.0 {
            // 工具可能比游戏晚启动，或落在备用端口：定期重读端口文件
            self.rescan_t = now;
            if let Some(p) = discover_port() {
                self.port = p;
                self.port_found = true;
            }
        }
        for s in 0..2 {
            if let Some((t, left)) = self.over[s] {
                let left = left - dt;
                self.over[s] = if left > 0.0 { Some((t, left)) } else { None };
            }
            let want = self.effective(s);
            let since = now - self.sent_t[s];
            let changed = self.sent[s] != Some(want);
            if (changed && since >= MIN_GAP) || since >= KEEPALIVE {
                self.send(s, want);
                self.sent[s] = Some(want);
                self.sent_t[s] = now;
            }
        }
    }

    fn send(&mut self, side: usize, t: Trig) {
        let wire_side = if side == L { 1 } else { 2 };
        let p = t.p;
        let msg = format!(
            "{{\"instructions\":[{{\"type\":1,\"parameters\":[0,{},19,{},{},{},{},{},{}]}}]}}",
            wire_side, t.mode, p[0], p[1], p[2], p[3], p[4]
        );
        if let Some(s) = &self.sock {
            if s.send_to(msg.as_bytes(), ("127.0.0.1", self.port)).is_ok() {
                self.packets += 1;
            }
        }
    }

    /// 退出前把两侧扳机还原成松弛。隔开两次发送以越过工具入口的限频窗口。
    pub fn shutdown(&mut self) {
        for _ in 0..2 {
            std::thread::sleep(std::time::Duration::from_millis(25));
            self.send(L, Trig::NORMAL);
            self.send(R, Trig::NORMAL);
        }
    }
}

struct Hit {
    lo: f32,
    hi: f32,
    dur: f32,
    t: f32,
}

/// 震动混音：若干一次性冲击（带衰减包络）+ 每帧由游戏状态给出的持续量
pub struct Rumble {
    hits: Vec<Hit>,
    /// 持续震动（低频大马达, 高频小马达），每帧由游戏重新设定，取用后清零
    pub cont: (f32, f32),
    pub scale: f32,
    /// 最近一次输出值（调试面板显示）
    pub out: (f32, f32),
}

impl Rumble {
    pub fn new() -> Rumble {
        Rumble { hits: Vec::new(), cont: (0.0, 0.0), scale: 1.0, out: (0.0, 0.0) }
    }

    /// 一次性冲击：(低频强度, 高频强度, 持续秒数)，强度 0..1
    pub fn hit(&mut self, h: (f32, f32, f32)) {
        if h.2 <= 0.0 {
            return;
        }
        if self.hits.len() > 24 {
            self.hits.remove(0);
        }
        self.hits.push(Hit { lo: h.0, hi: h.1, dur: h.2, t: 0.0 });
    }

    pub fn stop(&mut self) {
        self.hits.clear();
        self.cont = (0.0, 0.0);
    }

    pub fn update(&mut self, dt: f32) -> (f32, f32) {
        let (mut lo, mut hi) = self.cont;
        self.cont = (0.0, 0.0);
        for h in self.hits.iter_mut() {
            h.t += dt;
            let k = (1.0 - h.t / h.dur).max(0.0);
            let env = k * k; // 先猛后收：打击感比线性衰减干脆
            lo += h.lo * env;
            hi += h.hi * env;
        }
        self.hits.retain(|h| h.t < h.dur);
        self.out = ((lo * self.scale).clamp(0.0, 1.0), (hi * self.scale).clamp(0.0, 1.0));
        self.out
    }
}

// 全部手感参数已搬到 tune.rs（由档案里的 `feel` 配置驱动，默认值与原先的常量一致）。
