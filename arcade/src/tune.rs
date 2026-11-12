//! 手感配置（`feel`）。
//!
//! 扳机猎人和工具里的其他游戏一样，只是一个普通的游戏档案；它的手感写在档案的 `feel` 段里，
//! 导出 / 导入 / 保存都走工具通用的那一套。游戏启动时读取档案里的 `feel`，按 F5 可热重载。
//!
//! 找档案的规则：在 `%APPDATA%\Apex5Unleashed\games\*.json` 里找「exe 含 apex5-arcade.exe 且带
//! `feel`」的用户档案，取最新保存的一份；没有就用编进程序的默认值（与内置档案里的 `feel` 一致）。
//! 配置可以只写想改的部分，其余自动用默认值。
//!
//! 约定：扳机参数是飞智固件的原始量程 1..255；震动三元组是 `[低频, 高频, 持续秒]`，强度 0..1。
use crate::feel::Trig;
use serde::{Deserialize, Serialize};
use std::sync::{OnceLock, RwLock};

/// 一次性震动：[低频马达 0..1, 高频马达 0..1, 持续秒]
pub type Hit = [f32; 3];

/// 震动 / 后坐类扳机模式的四个参数
#[derive(Serialize, Deserialize, Clone, Copy, Debug)]
#[serde(default)]
pub struct Vib {
    /// 起效位置（行程）
    pub stroke: f32,
    /// 触发点
    pub press: f32,
    /// 力度
    pub strength: f32,
    /// 频率
    pub freq: f32,
}

/// 阻尼：起效位置 + 阻力（阻力 = resist_min + resist_gain × 某个 0..1 的量）
#[derive(Serialize, Deserialize, Clone, Copy, Debug)]
#[serde(default)]
pub struct Ramp {
    pub stroke: f32,
    pub resist_min: f32,
    pub resist_gain: f32,
}

/// 锁死：在 stroke 位置顶住
#[derive(Serialize, Deserialize, Clone, Copy, Debug)]
#[serde(default)]
pub struct Lock {
    pub stroke: f32,
    pub strength: f32,
}

/// 二段（狙击）：stroke 处一道坎，压过去后回弹 recoil_stroke
#[derive(Serialize, Deserialize, Clone, Copy, Debug)]
#[serde(default)]
pub struct Wall {
    pub stroke: f32,
    pub recoil_stroke: f32,
    pub strength: f32,
}

fn vib(stroke: f32, press: f32, strength: f32, freq: f32) -> Vib {
    Vib { stroke, press, strength, freq }
}

impl Default for Vib {
    fn default() -> Vib {
        vib(100.0, 50.0, 100.0, 30.0)
    }
}
impl Default for Ramp {
    fn default() -> Ramp {
        Ramp { stroke: 30.0, resist_min: 35.0, resist_gain: 200.0 }
    }
}
impl Default for Lock {
    fn default() -> Lock {
        Lock { stroke: 20.0, strength: 255.0 }
    }
}
impl Default for Wall {
    fn default() -> Wall {
        Wall { stroke: 100.0, recoil_stroke: 60.0, strength: 200.0 }
    }
}

// ───────────── 武器 ─────────────

/// 弓（RT）：拉得越深阻尼越大，拉满弓弦发颤，松手放箭
#[derive(Serialize, Deserialize, Clone, Copy, Debug)]
#[serde(default)]
pub struct Bow {
    /// 拉弓中：阻力 = resist_min + resist_gain × 拉弓量(0..1)
    pub draw: Ramp,
    /// 拉满弓后弓弦的细颤
    pub full: Vib,
    /// 拉满弓时握把的高频嗡鸣强度
    pub full_hum: f32,
    /// 放箭的握把震动：低频 = lo × 力度；高频 = hi_base + hi_gain × 力度；持续 dur 秒
    pub release_lo: f32,
    pub release_hi_base: f32,
    pub release_hi_gain: f32,
    pub release_dur: f32,
}
impl Default for Bow {
    fn default() -> Bow {
        Bow {
            draw: Ramp { stroke: 30.0, resist_min: 35.0, resist_gain: 200.0 },
            full: vib(120.0, 40.0, 70.0, 45.0),
            full_hum: 0.06,
            release_lo: 0.15,
            release_hi_base: 0.25,
            release_hi_gain: 0.45,
            release_dur: 0.09,
        }
    }
}

/// 左轮（RT）：半程一道坎是瞄准，压过去击发；空仓变软，装弹锁死
#[derive(Serialize, Deserialize, Clone, Copy, Debug)]
#[serde(default)]
pub struct Revolver {
    /// RT 按到这个深度算击发（0..1，应略高于坎的位置）
    pub fire_at: f32,
    /// 待发：坎
    pub ready: Wall,
    /// 击发瞬间的后坐（recoil 模式）与持续时间
    pub kick: Vib,
    pub kick_time: f32,
    /// 击发的握把震动
    pub shot: Hit,
    /// 空仓扣扳机的「咔」
    pub dry: Hit,
    /// 装弹中：扳机锁死
    pub reloading: Lock,
    /// 装弹总时长（秒）；每入膛一发有一下 reload_tick
    pub reload_time: f32,
    pub reload_tick: Hit,
}
impl Default for Revolver {
    fn default() -> Revolver {
        Revolver {
            fire_at: 0.78,
            ready: Wall { stroke: 100.0, recoil_stroke: 60.0, strength: 200.0 },
            kick: vib(200.0, 80.0, 230.0, 20.0),
            kick_time: 0.14,
            shot: [0.9, 0.6, 0.16],
            dry: [0.0, 0.25, 0.04],
            reloading: Lock { stroke: 20.0, strength: 255.0 },
            reload_time: 1.1,
            reload_tick: [0.0, 0.3, 0.035],
        }
    }
}

/// 加特林（RT）：扳机随射速震动，过热锁死
#[derive(Serialize, Deserialize, Clone, Copy, Debug)]
#[serde(default)]
pub struct Gatling {
    /// 待机：一点轻阻尼（stroke + resistance）
    pub idle_stroke: f32,
    pub idle_resistance: f32,
    /// 扫射（震动模式）：力度 = strength_base + strength_heat × 热量；频率 = freq_base + freq_spin × 转速
    pub fire_stroke: f32,
    pub fire_press: f32,
    pub fire_strength_base: f32,
    pub fire_strength_heat: f32,
    pub fire_freq_base: f32,
    pub fire_freq_spin: f32,
    /// 过热：扳机锁死
    pub overheat: Lock,
    /// 每发子弹的握把「嗒」
    pub tick: Hit,
    /// 枪管转动时的持续低频强度（乘以转速）
    pub spin_hum: f32,
    /// 刚过热的一下震动
    pub overheat_hit: Hit,
}
impl Default for Gatling {
    fn default() -> Gatling {
        Gatling {
            idle_stroke: 60.0,
            idle_resistance: 45.0,
            fire_stroke: 40.0,
            fire_press: 30.0,
            fire_strength_base: 90.0,
            fire_strength_heat: 120.0,
            fire_freq_base: 14.0,
            fire_freq_spin: 36.0,
            overheat: Lock { stroke: 15.0, strength: 255.0 },
            tick: [0.22, 0.32, 0.05],
            spin_hum: 0.10,
            overheat_hit: [0.5, 0.2, 0.35],
        }
    }
}

/// 喷气背包（LT）：推力随按压深度；燃料低发抖，烧光变软
#[derive(Serialize, Deserialize, Clone, Copy, Debug)]
#[serde(default)]
pub struct Jetpack {
    /// 正常：阻力 = resist_min + resist_gain × (1 − 燃料)，燃料越少越重
    pub draw: Ramp,
    /// 燃料低于此值（0..1）开始「喘」
    pub low_fuel: f32,
    /// 燃料见底的抖动
    pub sputter: Vib,
    /// 推力对应的握把持续低频（乘以推力）
    pub hum: f32,
}
impl Default for Jetpack {
    fn default() -> Jetpack {
        Jetpack {
            draw: Ramp { stroke: 25.0, resist_min: 50.0, resist_gain: 150.0 },
            low_fuel: 0.25,
            sputter: vib(20.0, 30.0, 120.0, 8.0),
            hum: 0.20,
        }
    }
}

// ───────────── 环境事件 ─────────────

/// 落地：低频 = lo_base + lo_gain × 下落速度(0..1)
#[derive(Serialize, Deserialize, Clone, Copy, Debug)]
#[serde(default)]
pub struct Land {
    pub lo_base: f32,
    pub lo_gain: f32,
    pub hi: f32,
    pub dur: f32,
}
impl Default for Land {
    fn default() -> Land {
        Land { lo_base: 0.15, lo_gain: 0.55, hi: 0.05, dur: 0.09 }
    }
}

/// 爆炸：低频 = lo × 接近度；高频 = hi × 接近度；时长 = dur_base + dur_gain × 接近度
#[derive(Serialize, Deserialize, Clone, Copy, Debug)]
#[serde(default)]
pub struct Blast {
    pub lo: f32,
    pub hi: f32,
    pub dur_base: f32,
    pub dur_gain: f32,
}
impl Default for Blast {
    fn default() -> Blast {
        Blast { lo: 1.0, hi: 0.6, dur_base: 0.25, dur_gain: 0.35 }
    }
}

/// Boss 跺地：低频 = lo × 接近度；高频 = hi × 接近度
#[derive(Serialize, Deserialize, Clone, Copy, Debug)]
#[serde(default)]
pub struct Stomp {
    pub lo: f32,
    pub hi: f32,
    pub dur: f32,
}
impl Default for Stomp {
    fn default() -> Stomp {
        Stomp { lo: 1.0, hi: 0.45, dur: 0.5 }
    }
}

#[derive(Serialize, Deserialize, Clone, Copy, Debug)]
#[serde(default)]
pub struct Events {
    pub land: Land,
    pub jump: Hit,
    /// 命中敌人的确认感
    pub hit_confirm: Hit,
    pub kill: Hit,
    /// 受伤：握把震动 + 双扳机一下后坐
    pub hurt: Hit,
    pub hurt_kick: Vib,
    pub hurt_kick_time: f32,
    pub explosion: Blast,
    /// 爆炸 / 跺地时双扳机的冲击（震动模式）、接近度门槛、持续时间
    pub shock: Vib,
    pub shock_near: f32,
    pub shock_time: f32,
    pub stomp: Stomp,
    /// Boss 咆哮：握把长震 + 双扳机低沉震动
    pub roar: Hit,
    pub roar_trigger: Vib,
    pub roar_time: f32,
    /// 闸门开合
    pub gate: Hit,
    pub checkpoint: Hit,
    pub pickup: Hit,
    /// 低血量心跳（每秒两下）
    pub heartbeat: Hit,
    /// 石块落地（乘以接近度）
    pub rock_land: Hit,
    /// 设置里调节强度时的试震
    pub test: Hit,
}
impl Default for Events {
    fn default() -> Events {
        Events {
            land: Land::default(),
            jump: [0.0, 0.12, 0.04],
            hit_confirm: [0.0, 0.18, 0.05],
            kill: [0.2, 0.25, 0.08],
            hurt: [0.85, 0.85, 0.28],
            hurt_kick: vib(60.0, 20.0, 230.0, 30.0),
            hurt_kick_time: 0.16,
            explosion: Blast::default(),
            shock: vib(10.0, 255.0, 200.0, 30.0),
            shock_near: 0.25,
            shock_time: 0.30,
            stomp: Stomp::default(),
            roar: [0.6, 0.2, 1.0],
            roar_trigger: vib(10.0, 255.0, 130.0, 12.0),
            roar_time: 0.9,
            gate: [0.45, 0.1, 0.35],
            checkpoint: [0.0, 0.35, 0.12],
            pickup: [0.0, 0.25, 0.08],
            heartbeat: [0.3, 0.0, 0.07],
            rock_land: [0.4, 0.15, 0.12],
            test: [0.7, 0.7, 0.25],
        }
    }
}

/// 整份手感配置 = 档案里的 `feel` 段
#[derive(Serialize, Deserialize, Clone, Copy, Debug, Default)]
#[serde(default)]
pub struct Feel {
    pub bow: Bow,
    pub revolver: Revolver,
    pub gatling: Gatling,
    pub jetpack: Jetpack,
    pub events: Events,
}

// ───────────── 全局配置 + 加载 ─────────────

fn cell() -> &'static RwLock<Feel> {
    static CELL: OnceLock<RwLock<Feel>> = OnceLock::new();
    CELL.get_or_init(|| RwLock::new(Feel::default()))
}

fn get<R>(f: impl FnOnce(&Feel) -> R) -> R {
    let g = cell().read().unwrap_or_else(|e| e.into_inner());
    f(&g)
}

/// 默认配置的 JSON 文本（`--dump-feel` 用，也是内置档案 `feel` 段的来源）
pub fn default_json() -> String {
    serde_json::to_string_pretty(&Feel::default()).unwrap_or_default()
}

/// 当前实际生效的配置（`--show-feel` 用：确认档案里的 `feel` 被读到了）
pub fn effective_json() -> String {
    get(|f| serde_json::to_string_pretty(f).unwrap_or_default())
}

/// 本次加载的结果，给界面提示用
pub struct Loaded {
    /// "内置默认" 或 档案名
    pub source: String,
    pub error: Option<String>,
}

/// 读取档案里的 `feel` 并生效；失败就保持默认并把原因带回去
pub fn load() -> Loaded {
    let mut best: Option<(f64, String, serde_json::Value)> = None;
    let mut error = None;
    let base = std::env::var("APPDATA").unwrap_or_default();
    let dir = std::path::Path::new(&base).join("Apex5Unleashed").join("games");
    if let Ok(rd) = std::fs::read_dir(&dir) {
        for e in rd.flatten() {
            let p = e.path();
            if p.extension().and_then(|s| s.to_str()) != Some("json") {
                continue;
            }
            let Ok(text) = std::fs::read_to_string(&p) else {
                continue;
            };
            let Ok(v) = serde_json::from_str::<serde_json::Value>(&text) else {
                continue;
            };
            let mine = v
                .get("exe")
                .and_then(|x| x.as_array())
                .map(|a| a.iter().any(|s| s.as_str().map(|s| s.eq_ignore_ascii_case("apex5-arcade.exe")).unwrap_or(false)))
                .unwrap_or(false);
            let Some(feel) = v.get("feel").filter(|f| f.is_object()) else {
                continue;
            };
            if !mine {
                continue;
            }
            let stamp = v
                .get("saved_at")
                .and_then(|x| x.as_f64())
                .or_else(|| {
                    e.metadata()
                        .ok()
                        .and_then(|m| m.modified().ok())
                        .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
                        .map(|d| d.as_secs_f64())
                })
                .unwrap_or(0.0);
            let name = p.file_name().and_then(|s| s.to_str()).unwrap_or("?").to_string();
            if best.as_ref().map(|b| stamp > b.0).unwrap_or(true) {
                best = Some((stamp, name, feel.clone()));
            }
        }
    }
    let (feel, source) = match best {
        Some((_, name, v)) => match serde_json::from_value::<Feel>(v) {
            Ok(f) => (f, name),
            Err(e) => {
                error = Some(format!("{}: {}", name, e));
                (Feel::default(), "内置默认".to_string())
            }
        },
        None => (Feel::default(), "内置默认".to_string()),
    };
    *cell().write().unwrap_or_else(|e| e.into_inner()) = feel;
    Loaded { source, error }
}

// ───────────── 对外的取值函数（游戏代码只调这些）─────────────

fn h(a: Hit) -> (f32, f32, f32) {
    (a[0], a[1], a[2])
}

pub fn bow_draw(d: f32) -> Trig {
    get(|f| Trig::race(f.bow.draw.stroke, f.bow.draw.resist_min + f.bow.draw.resist_gain * d))
}
pub fn bow_full() -> Trig {
    get(|f| Trig::vibration(f.bow.full.stroke, f.bow.full.press, f.bow.full.strength, f.bow.full.freq))
}
pub fn bow_full_hum() -> f32 {
    get(|f| f.bow.full_hum)
}
pub fn bow_release(pow: f32) -> (f32, f32, f32) {
    get(|f| (f.bow.release_lo * pow, f.bow.release_hi_base + f.bow.release_hi_gain * pow, f.bow.release_dur))
}

pub fn rev_fire_at() -> f32 {
    get(|f| f.revolver.fire_at)
}
pub fn rev_ready() -> Trig {
    get(|f| Trig::sniper(f.revolver.ready.stroke, f.revolver.ready.recoil_stroke, f.revolver.ready.strength))
}
pub fn rev_kick() -> Trig {
    get(|f| Trig::recoil(f.revolver.kick.stroke, f.revolver.kick.press, f.revolver.kick.strength, f.revolver.kick.freq))
}
pub fn rev_kick_time() -> f32 {
    get(|f| f.revolver.kick_time)
}
pub fn rev_shot() -> (f32, f32, f32) {
    get(|f| h(f.revolver.shot))
}
pub fn rev_empty() -> Trig {
    Trig::NORMAL
}
pub fn rev_dry() -> (f32, f32, f32) {
    get(|f| h(f.revolver.dry))
}
pub fn rev_reloading() -> Trig {
    get(|f| Trig::lock(f.revolver.reloading.stroke, f.revolver.reloading.strength))
}
pub fn rev_reload_time() -> f32 {
    get(|f| f.revolver.reload_time)
}
pub fn rev_reload_tick() -> (f32, f32, f32) {
    get(|f| h(f.revolver.reload_tick))
}

pub fn gat_idle() -> Trig {
    get(|f| Trig::race(f.gatling.idle_stroke, f.gatling.idle_resistance))
}
pub fn gat_fire(spin: f32, heat: f32) -> Trig {
    get(|f| {
        let g = &f.gatling;
        Trig::vibration(g.fire_stroke, g.fire_press, g.fire_strength_base + g.fire_strength_heat * heat, g.fire_freq_base + g.fire_freq_spin * spin)
    })
}
pub fn gat_overheat() -> Trig {
    get(|f| Trig::lock(f.gatling.overheat.stroke, f.gatling.overheat.strength))
}
pub fn gat_tick() -> (f32, f32, f32) {
    get(|f| h(f.gatling.tick))
}
pub fn gat_spin_hum() -> f32 {
    get(|f| f.gatling.spin_hum)
}
pub fn gat_overheat_hit() -> (f32, f32, f32) {
    get(|f| h(f.gatling.overheat_hit))
}

pub fn jet(fuel: f32) -> Trig {
    get(|f| Trig::race(f.jetpack.draw.stroke, f.jetpack.draw.resist_min + f.jetpack.draw.resist_gain * (1.0 - fuel)))
}
pub fn jet_low_fuel() -> f32 {
    get(|f| f.jetpack.low_fuel)
}
pub fn jet_sputter() -> Trig {
    get(|f| Trig::vibration(f.jetpack.sputter.stroke, f.jetpack.sputter.press, f.jetpack.sputter.strength, f.jetpack.sputter.freq))
}
pub fn jet_empty() -> Trig {
    Trig::NORMAL
}
pub fn jet_hum() -> f32 {
    get(|f| f.jetpack.hum)
}

pub fn land(v: f32) -> (f32, f32, f32) {
    get(|f| (f.events.land.lo_base + f.events.land.lo_gain * v, f.events.land.hi, f.events.land.dur))
}
pub fn jump() -> (f32, f32, f32) {
    get(|f| h(f.events.jump))
}
pub fn hit_confirm() -> (f32, f32, f32) {
    get(|f| h(f.events.hit_confirm))
}
pub fn kill() -> (f32, f32, f32) {
    get(|f| h(f.events.kill))
}
pub fn hurt() -> (f32, f32, f32) {
    get(|f| h(f.events.hurt))
}
pub fn hurt_kick() -> Trig {
    get(|f| Trig::recoil(f.events.hurt_kick.stroke, f.events.hurt_kick.press, f.events.hurt_kick.strength, f.events.hurt_kick.freq))
}
pub fn hurt_kick_time() -> f32 {
    get(|f| f.events.hurt_kick_time)
}
pub fn explosion(near: f32) -> (f32, f32, f32) {
    get(|f| {
        let b = &f.events.explosion;
        (b.lo * near, b.hi * near, b.dur_base + b.dur_gain * near)
    })
}
pub fn shock() -> Trig {
    get(|f| Trig::vibration(f.events.shock.stroke, f.events.shock.press, f.events.shock.strength, f.events.shock.freq))
}
pub fn shock_near() -> f32 {
    get(|f| f.events.shock_near)
}
pub fn shock_time() -> f32 {
    get(|f| f.events.shock_time)
}
pub fn stomp(near: f32) -> (f32, f32, f32) {
    get(|f| (f.events.stomp.lo * near, f.events.stomp.hi * near, f.events.stomp.dur))
}
pub fn roar() -> (f32, f32, f32) {
    get(|f| h(f.events.roar))
}
pub fn roar_trig() -> Trig {
    get(|f| Trig::vibration(f.events.roar_trigger.stroke, f.events.roar_trigger.press, f.events.roar_trigger.strength, f.events.roar_trigger.freq))
}
pub fn roar_time() -> f32 {
    get(|f| f.events.roar_time)
}
pub fn gate() -> (f32, f32, f32) {
    get(|f| h(f.events.gate))
}
pub fn checkpoint() -> (f32, f32, f32) {
    get(|f| h(f.events.checkpoint))
}
pub fn pickup() -> (f32, f32, f32) {
    get(|f| h(f.events.pickup))
}
pub fn heartbeat() -> (f32, f32, f32) {
    get(|f| h(f.events.heartbeat))
}
pub fn rock_land() -> (f32, f32, f32) {
    get(|f| h(f.events.rock_land))
}
pub fn test() -> (f32, f32, f32) {
    get(|f| h(f.events.test))
}
