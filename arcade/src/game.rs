//! 游戏世界：玩家与三把武器、敌人与 Boss、弹幕、粒子、关卡流程，以及全部绘制。
//! 每把武器 / 喷气背包在 `update_player` 里把「此刻扳机该是什么手感」交给 `feel::Dsx`，
//! 把「此刻该怎么震」交给 `feel::Rumble`——具体数值都在 `feel::tune`。
use crate::feel::{Dsx, Rumble, Trig, L, R};
use crate::tune;
use crate::gfx::*;
use crate::level::*;
use crate::pad::Input;
use crate::sfx::{Sfx, S};
use macroquad::prelude::*;

pub struct Fx<'a> {
    pub dsx: &'a mut Dsx,
    pub rum: &'a mut Rumble,
    pub sfx: &'a mut Sfx,
}

/// 画 HUD 需要的外部状态（由 main 每帧填好）
pub struct Hud {
    pub lt: f32,
    pub rt: f32,
    pub trig: [Trig; 2],
    pub rum: (f32, f32),
    pub port: u16,
    pub port_found: bool,
    pub packets: u32,
    pub pads: u32,
    pub detail: bool,
}

const GRAV: f32 = 900.0;
/// 玩家碰撞盒
const PW: f32 = 8.0;
const PH: f32 = 13.0;
const MAX_HP: i32 = 6;
/// 地面顶边的像素 y
const FLOOR: f32 = 9.0 * TS;

// 巨像状态
const G_SLEEP: u8 = 0;
const G_INTRO: u8 = 1;
const G_WALK: u8 = 2;
const G_STOMP_TELE: u8 = 3;
const G_STOMP_REC: u8 = 4;
const G_THROW: u8 = 5;
const G_CHARGE_TELE: u8 = 6;
const G_CHARGE: u8 = 7;
const G_STUN: u8 = 8;
const G_DYING: u8 = 9;

const WAVES: [u32; 3] = [6, 9, 12];

fn approach(v: f32, target: f32, step: f32) -> f32 {
    if v < target {
        (v + step).min(target)
    } else {
        (v - step).max(target)
    }
}

fn rf(a: f32, b: f32) -> f32 {
    rand::gen_range(a, b)
}

fn hash(n: u32) -> u32 {
    let mut x = n.wrapping_mul(0x9e37_79b1) ^ 0x85eb_ca6b;
    x ^= x >> 15;
    x = x.wrapping_mul(0x2c1b_3c6d);
    x ^= x >> 12;
    x
}

fn mix(a: u32, b: u32, k: f32) -> Color {
    let (ca, cb) = (rgb(a), rgb(b));
    let k = k.clamp(0.0, 1.0);
    Color::new(ca.r + (cb.r - ca.r) * k, ca.g + (cb.g - ca.g) * k, ca.b + (cb.b - ca.b) * k, 1.0)
}

fn overlap(ax: f32, ay: f32, aw: f32, ah: f32, bx: f32, by: f32, bw: f32, bh: f32) -> bool {
    ax < bx + bw && ax + aw > bx && ay < by + bh && ay + ah > by
}

#[derive(Clone, Copy, PartialEq)]
pub enum Weapon {
    Bow,
    Revolver,
    Gatling,
}

impl Weapon {
    fn idx(self) -> usize {
        match self {
            Weapon::Bow => 0,
            Weapon::Revolver => 1,
            Weapon::Gatling => 2,
        }
    }
    fn from(i: usize) -> Weapon {
        match i % 3 {
            0 => Weapon::Bow,
            1 => Weapon::Revolver,
            _ => Weapon::Gatling,
        }
    }
}

pub struct Player {
    x: f32,
    y: f32,
    vx: f32,
    vy: f32,
    face: f32,
    ground: bool,
    jumping: bool,
    coyote: f32,
    jbuf: f32,
    hp: i32,
    inv: f32,
    dead: f32,
    weapon: Weapon,
    aim: f32,
    // 弓
    draw: f32,
    full_ping: bool,
    // 左轮
    ammo: i32,
    reload: f32,
    latch: bool,
    aiming: bool,
    // 加特林
    spin: f32,
    heat: f32,
    over: bool,
    shot_cd: f32,
    // 喷气背包
    fuel: f32,
    thrust: f32,
    ground_t: f32,
    anim: f32,
    flash: f32,
    beat: f32,
    safe: (f32, f32),
}

impl Player {
    fn new(x: f32, y: f32) -> Player {
        Player {
            x,
            y,
            vx: 0.0,
            vy: 0.0,
            face: 1.0,
            ground: false,
            jumping: false,
            coyote: 0.0,
            jbuf: 0.0,
            hp: MAX_HP,
            inv: 0.0,
            dead: 0.0,
            weapon: Weapon::Bow,
            aim: 0.0,
            draw: 0.0,
            full_ping: false,
            ammo: 6,
            reload: 0.0,
            latch: false,
            aiming: false,
            spin: 0.0,
            heat: 0.0,
            over: false,
            shot_cd: 0.0,
            fuel: 1.0,
            thrust: 0.0,
            ground_t: 0.0,
            anim: 0.0,
            flash: 0.0,
            beat: 0.0,
            safe: (x, y),
        }
    }

    /// 枪口：（世界坐标 x, y, 方向 dx, dy）
    fn muzzle(&self, lvl: &Level) -> (f32, f32, f32, f32) {
        let (dx, dy) = (self.aim.cos() * self.face, self.aim.sin());
        let (hx, hy) = (self.x + PW / 2.0 + self.face * 2.0, self.y + 7.0);
        let (mx, my) = (hx + dx * 8.0, hy + dy * 8.0);
        if lvl.solid_px(mx, my) {
            (hx, hy, dx, dy)
        } else {
            (mx, my, dx, dy)
        }
    }
}

struct Enemy {
    id: u32,
    k: EK,
    x: f32,
    y: f32,
    w: f32,
    h: f32,
    vx: f32,
    vy: f32,
    hp: f32,
    max_hp: f32,
    group: u8,
    /// 通用计时器（史莱姆跳跃间隔 / 蝙蝠撤退 / 炮台冷却 / 巨像投石间隔）
    t: f32,
    st: u8,
    st_t: f32,
    n: i32,
    face: f32,
    flash: f32,
    ground: bool,
    home: (f32, f32),
    dead: bool,
}

/// 以「底边中点」为锚点生成一个敌人
fn make_enemy(id: u32, k: EK, cx: f32, bottom: f32, group: u8) -> Enemy {
    let (w, h, hp) = match k {
        EK::Dummy => (10.0, 14.0, 1.0),
        EK::Slime => (12.0, 8.0, 3.0),
        EK::Bat => (12.0, 6.0, 2.0),
        EK::Turret => (12.0, 10.0, 8.0),
        EK::Barrel => (10.0, 12.0, 1.0),
        EK::Golem => (28.0, 34.0, 140.0),
    };
    let (x, y) = (cx - w / 2.0, bottom - h);
    Enemy {
        id,
        k,
        x,
        y,
        w,
        h,
        vx: 0.0,
        vy: 0.0,
        hp,
        max_hp: hp,
        group,
        t: rf(0.2, 1.0),
        st: 0,
        st_t: 0.0,
        n: 0,
        face: -1.0,
        flash: 0.0,
        ground: false,
        home: (x, y),
        dead: false,
    }
}

#[derive(Clone, Copy, PartialEq)]
enum PK {
    Arrow,
    Bullet,
    Gat,
    Orb,
    Rock,
    Wave,
}

struct Proj {
    k: PK,
    x: f32,
    y: f32,
    vx: f32,
    vy: f32,
    dmg: f32,
    life: f32,
    player: bool,
    pierce: i32,
    last_hit: u32,
    stuck: bool,
    dead: bool,
}

impl Proj {
    fn new(k: PK, x: f32, y: f32, vx: f32, vy: f32, dmg: f32, life: f32, player: bool) -> Proj {
        Proj { k, x, y, vx, vy, dmg, life, player, pierce: 0, last_hit: u32::MAX, stuck: false, dead: false }
    }
}

struct Part {
    x: f32,
    y: f32,
    vx: f32,
    vy: f32,
    life: f32,
    max: f32,
    col: u32,
    size: f32,
    grav: f32,
}

fn burst(parts: &mut Vec<Part>, x: f32, y: f32, n: usize, col: u32, spd: f32, life: f32, grav: f32) {
    for _ in 0..n {
        if parts.len() > 600 {
            return;
        }
        let a = rf(0.0, std::f32::consts::TAU);
        let s = rf(spd * 0.3, spd);
        let l = rf(life * 0.5, life);
        parts.push(Part {
            x,
            y,
            vx: a.cos() * s,
            vy: a.sin() * s,
            life: l,
            max: l,
            col,
            size: if rf(0.0, 1.0) < 0.3 { 2.0 } else { 1.0 },
            grav,
        });
    }
}

struct Floater {
    x: f32,
    y: f32,
    life: f32,
    col: u32,
    cn: String,
    en: String,
}

#[derive(Default)]
struct Arena {
    /// 0 未开始 / 1 进行中 / 2 已清场
    state: u8,
    wave: usize,
    left: u32,
    spawn_t: f32,
    gap: f32,
}

#[derive(Default)]
pub struct Stats {
    pub time: f32,
    pub kills: u32,
    pub shots: u32,
    pub hits: u32,
    pub deaths: u32,
}

pub struct World {
    lvl: Level,
    p: Player,
    en: Vec<Enemy>,
    pr: Vec<Proj>,
    parts: Vec<Part>,
    floats: Vec<Floater>,
    booms: Vec<(f32, f32)>,
    hurt_q: Option<(i32, f32)>,
    cam: f32,
    shake: f32,
    t: f32,
    pub stats: Stats,
    /// 各组：尚未刷出的敌人数 / 是否已开始 / 是否已清完
    pending: [u32; 8],
    started: [bool; 8],
    done: [bool; 8],
    arena: Arena,
    boss_awake: bool,
    win_t: f32,
    pub won: bool,
    cp: (f32, f32),
    cp_idx: i32,
    sign: Option<usize>,
    banner: (String, String, f32),
    next_id: u32,
}

impl World {
    pub fn new() -> World {
        let lvl = Level::build();
        let mut w = World {
            p: Player::new(lvl.start.0, lvl.start.1),
            cp: lvl.start,
            lvl,
            en: Vec::new(),
            pr: Vec::new(),
            parts: Vec::new(),
            floats: Vec::new(),
            booms: Vec::new(),
            hurt_q: None,
            cam: 0.0,
            shake: 0.0,
            t: 0.0,
            stats: Stats::default(),
            pending: [0; 8],
            started: [false; 8],
            done: [false; 8],
            arena: Arena::default(),
            boss_awake: false,
            win_t: 0.0,
            won: false,
            cp_idx: -1,
            sign: None,
            banner: (String::new(), String::new(), 0.0),
            next_id: 1,
        };
        for i in 0..w.lvl.spawns.len() {
            let (k, tx, ty, group) = {
                let s = &w.lvl.spawns[i];
                (s.k, s.tx, s.ty, s.group)
            };
            w.spawn(k, tx as f32 * TS + 8.0, (ty + 1) as f32 * TS, group);
        }
        w
    }

    fn spawn(&mut self, k: EK, cx: f32, bottom: f32, group: u8) {
        let id = self.next_id;
        self.next_id += 1;
        self.en.push(make_enemy(id, k, cx, bottom, group));
        self.started[group as usize & 7] = true;
    }

    fn say(&mut self, cn: &str, en: &str) {
        self.banner = (cn.to_string(), en.to_string(), 2.2);
    }

    /// 回到最近的存档点（暂停菜单也会调用）
    pub fn respawn(&mut self) {
        let (x, y) = self.cp;
        let w = self.p.weapon;
        self.p = Player::new(x, y);
        self.p.weapon = w;
        self.p.inv = 1.5;
        self.pr.retain(|q| q.player);
        // 没打完的遭遇战整场重来，否则玩家会被关在闸门外
        if self.arena.state == 1 {
            self.arena = Arena::default();
            self.en.retain(|e| e.group != G_ARENA);
            self.pending[G_ARENA as usize] = 0;
            self.started[G_ARENA as usize] = false;
        }
        if self.boss_awake && !self.done[G_BOSS as usize] {
            self.boss_awake = false;
            for e in self.en.iter_mut() {
                if e.k == EK::Golem {
                    e.hp = e.max_hp;
                    e.st = G_SLEEP;
                    e.x = e.home.0;
                    e.y = e.home.1;
                    e.vx = 0.0;
                    e.vy = 0.0;
                }
            }
        }
        for g in self.lvl.gates.iter_mut() {
            if g.close_x.is_some() && !self.done[g.group as usize & 7] {
                g.closed = false;
                g.triggered = false;
            }
        }
    }

    pub fn update(&mut self, inp: &Input, dt: f32, fx: &mut Fx) {
        self.t += dt;
        if self.won {
            return;
        }
        self.stats.time += dt;
        self.update_player(inp, dt, fx);
        self.update_enemies(dt, fx);
        self.update_projs(dt, fx);
        self.process_booms(fx);
        self.reap(fx);
        if let Some((dmg, from_x)) = self.hurt_q.take() {
            self.damage_player(dmg, from_x, fx);
        }
        self.update_world(dt, fx);
        self.update_cam(dt);
    }

    // ───────────────────────── 玩家 ─────────────────────────

    fn update_player(&mut self, inp: &Input, dt: f32, fx: &mut Fx) {
        if self.p.dead > 0.0 {
            self.p.dead -= dt;
            fx.dsx.relax();
            fx.sfx.jet(0.0);
            if self.p.dead <= 0.0 {
                self.respawn();
            }
            return;
        }
        let mut fell = false;
        {
            let World { p, lvl, pr, parts, stats, .. } = self;
            p.inv = (p.inv - dt).max(0.0);
            p.flash = (p.flash - dt).max(0.0);
            p.shot_cd = (p.shot_cd - dt).max(0.0);
            p.anim += dt;

            // 切换武器
            let mut w = p.weapon.idx();
            if inp.next_w {
                w = (w + 1) % 3;
            }
            if inp.prev_w {
                w = (w + 2) % 3;
            }
            if let Some(i) = inp.pick_w {
                w = i % 3;
            }
            if w != p.weapon.idx() {
                p.weapon = Weapon::from(w);
                p.draw = 0.0;
                p.reload = 0.0;
                p.spin = 0.0;
                p.aiming = false;
                p.latch = true; // 切枪时若还按着 RT，不立刻走火
                fx.sfx.play(S::Ui);
            }

            // 跑动：拉弓 / 瞄准时放慢
            let slow = (p.weapon == Weapon::Bow && p.draw > 0.05) || p.aiming;
            let top = if slow { 45.0 } else { 95.0 };
            let acc = if p.ground { 900.0 } else { 520.0 };
            p.vx = approach(p.vx, inp.mx * top, acc * dt);
            if inp.mx.abs() > 0.3 {
                p.face = inp.mx.signum();
            }

            // 跳跃：带输入缓冲和土狼时间，松手提前收跳
            if inp.jump_p {
                p.jbuf = 0.12;
            }
            p.jbuf -= dt;
            p.coyote -= dt;
            if p.ground {
                p.coyote = 0.1;
            }
            if p.jbuf > 0.0 && p.coyote > 0.0 {
                p.vy = -255.0;
                p.jbuf = 0.0;
                p.coyote = 0.0;
                p.ground = false;
                p.jumping = true;
                fx.sfx.play(S::Jump);
                fx.rum.hit(tune::jump());
                burst(parts, p.x + PW / 2.0, p.y + PH, 4, pal::GRAY, 30.0, 0.25, 0.0);
            }
            if p.jumping && !inp.jump && p.vy < -90.0 {
                p.vy = -90.0;
            }
            if p.vy >= 0.0 {
                p.jumping = false;
            }

            // 喷气背包（LT 模拟量 = 推力）
            p.thrust = 0.0;
            if inp.lt > 0.06 && p.fuel > 0.0 {
                p.thrust = inp.lt;
                p.vy -= (GRAV * 0.55 + 950.0 * inp.lt) * dt;
                p.vy = p.vy.max(-140.0);
                p.fuel = (p.fuel - (0.16 + 0.30 * inp.lt) * dt).max(0.0);
                p.ground_t = 0.0;
                p.jumping = false;
                if parts.len() < 500 {
                    parts.push(Part {
                        x: p.x + PW / 2.0 - p.face * 3.0 + rf(-1.0, 1.0),
                        y: p.y + PH - 2.0,
                        vx: rf(-12.0, 12.0),
                        vy: rf(60.0, 120.0),
                        life: 0.25,
                        max: 0.25,
                        col: if rf(0.0, 1.0) < 0.5 { pal::ORANGE } else { pal::YELLOW },
                        size: 2.0,
                        grav: 0.0,
                    });
                }
            }

            // 重力 + 碰撞
            p.vy = (p.vy + GRAV * dt).min(420.0);
            let fall_v = p.vy;
            let was_ground = p.ground;
            let (hit_x, hit_y) = lvl.move_rect(&mut p.x, &mut p.y, PW, PH, p.vx * dt, p.vy * dt);
            if hit_x {
                p.vx = 0.0;
            }
            if hit_y {
                if p.vy > 0.0 {
                    if !was_ground && fall_v > 140.0 {
                        let v = ((fall_v - 140.0) / 280.0).clamp(0.0, 1.0);
                        fx.rum.hit(tune::land(v));
                        fx.sfx.play_v(S::Land, 0.4 + 0.6 * v);
                        burst(parts, p.x + PW / 2.0, p.y + PH, 3 + (v * 6.0) as usize, pal::GRAY, 40.0, 0.3, 0.0);
                    }
                    p.ground = true;
                    p.jumping = false;
                } else {
                    p.ground = false;
                }
                p.vy = 0.0;
            } else {
                p.ground = false;
            }
            if p.ground {
                p.ground_t += dt;
                if p.ground_t > 0.15 {
                    p.fuel = (p.fuel + 1.1 * dt).min(1.0);
                }
                if lvl.solid_px(p.x, p.y + PH + 2.0) && lvl.solid_px(p.x + PW, p.y + PH + 2.0) {
                    p.safe = (p.x, p.y);
                }
            } else {
                p.ground_t = 0.0;
            }
            if p.y > LH as f32 * TS + 24.0 {
                fell = true;
            }

            // 瞄准角：弓默认略微上扬，摇杆上下再调
            let target = match p.weapon {
                Weapon::Bow => -(0.17 + inp.my * 0.75),
                _ => -inp.my * 0.5,
            };
            p.aim = approach(p.aim, target, 4.0 * dt);
            let (mx, my, dx, dy) = p.muzzle(lvl);

            let rt = inp.rt;
            let mut cont = (0.0f32, 0.0f32);
            if p.weapon != Weapon::Gatling {
                p.heat = (p.heat - 0.35 * dt).max(0.0);
                if p.heat < 0.25 {
                    p.over = false;
                }
            }
            match p.weapon {
                Weapon::Bow => {
                    if rt > 0.1 {
                        // 拉得快、松得慢：缓缓回一点扳机不会立刻泄力
                        let rate = if rt > p.draw { 3.2 } else { 0.9 };
                        p.draw = approach(p.draw, rt, rate * dt);
                    } else if p.draw > 0.0 {
                        if p.draw >= 0.15 {
                            let pow = p.draw;
                            let sp = 170.0 + 290.0 * pow;
                            let mut a = Proj::new(PK::Arrow, mx, my, dx * sp, dy * sp, (2.0 + 6.0 * pow).round(), 3.5, true);
                            if pow >= 0.97 {
                                a.pierce = 2; // 满弓穿透
                            }
                            pr.push(a);
                            stats.shots += 1;
                            fx.rum.hit(tune::bow_release(pow));
                            fx.sfx.play_v(S::Bow, 0.5 + 0.5 * pow);
                        }
                        p.draw = 0.0;
                    }
                    if p.draw >= 0.97 {
                        fx.dsx.set(R, tune::bow_full());
                        cont.1 += tune::bow_full_hum();
                        if !p.full_ping {
                            p.full_ping = true;
                            fx.sfx.play(S::Tick);
                        }
                    } else {
                        p.full_ping = false;
                        fx.dsx.set(R, tune::bow_draw(p.draw));
                    }
                }
                Weapon::Revolver => {
                    p.aiming = false;
                    if p.reload > 0.0 {
                        let seg = tune::rev_reload_time() / 6.0;
                        let before = (p.reload / seg).floor();
                        p.reload -= dt;
                        if (p.reload.max(0.0) / seg).floor() != before {
                            fx.rum.hit(tune::rev_reload_tick());
                            fx.sfx.play(S::Tick);
                        }
                        fx.dsx.set(R, tune::rev_reloading());
                        if p.reload <= 0.0 {
                            p.reload = 0.0;
                            p.ammo = 6;
                            p.latch = true;
                            fx.sfx.play(S::Reload);
                        }
                    } else if p.ammo > 0 {
                        fx.dsx.set(R, tune::rev_ready());
                        if rt >= tune::rev_fire_at() && !p.latch {
                            p.latch = true;
                            p.ammo -= 1;
                            pr.push(Proj::new(PK::Bullet, mx, my, dx * 560.0, dy * 560.0, 6.0, 0.6, true));
                            stats.shots += 1;
                            p.flash = 0.07;
                            p.vx -= p.face * 40.0;
                            fx.dsx.kick(R, tune::rev_kick(), tune::rev_kick_time());
                            fx.rum.hit(tune::rev_shot());
                            fx.sfx.play(S::Gun);
                            burst(parts, mx, my, 5, pal::YELLOW, 70.0, 0.15, 0.0);
                        } else if rt > 0.15 && !p.latch {
                            p.aiming = true;
                        }
                    } else {
                        fx.dsx.set(R, tune::rev_empty());
                        if rt >= tune::rev_fire_at() && !p.latch {
                            p.latch = true;
                            fx.sfx.play(S::Dry);
                            fx.rum.hit(tune::rev_dry());
                        }
                    }
                    if rt < 0.35 {
                        p.latch = false;
                    }
                    if inp.reload && p.reload <= 0.0 && p.ammo < 6 {
                        p.reload = tune::rev_reload_time();
                    }
                }
                Weapon::Gatling => {
                    if p.over {
                        p.spin = (p.spin - 2.5 * dt).max(0.0);
                        p.heat = (p.heat - 0.45 * dt).max(0.0);
                        if p.heat < 0.25 {
                            p.over = false;
                        }
                        fx.dsx.set(R, tune::gat_overheat());
                        if rf(0.0, 1.0) < 0.3 && parts.len() < 500 {
                            parts.push(Part { x: mx, y: my, vx: rf(-8.0, 8.0), vy: rf(-40.0, -15.0), life: 0.5, max: 0.5, col: pal::WHITE, size: 1.0, grav: 0.0 });
                        }
                    } else {
                        if rt > 0.3 {
                            p.spin = (p.spin + 1.6 * dt).min(1.0);
                            p.heat += (0.16 + 0.16 * p.spin) * dt;
                            if p.shot_cd <= 0.0 {
                                p.shot_cd = 1.0 / (5.0 + 13.0 * p.spin);
                                let a = p.aim + rf(-0.07, 0.07);
                                pr.push(Proj::new(PK::Gat, mx, my, a.cos() * p.face * 430.0, a.sin() * 430.0, 1.0, 0.5, true));
                                stats.shots += 1;
                                p.flash = 0.04;
                                p.vx -= p.face * 6.0;
                                fx.rum.hit(tune::gat_tick());
                                fx.sfx.play_v(S::Gat, 0.7);
                            }
                            if p.heat >= 1.0 {
                                p.heat = 1.0;
                                p.over = true;
                                fx.rum.hit(tune::gat_overheat_hit());
                                fx.sfx.play(S::Hiss);
                            }
                        } else {
                            p.spin = (p.spin - 2.5 * dt).max(0.0);
                            p.heat = (p.heat - 0.35 * dt).max(0.0);
                        }
                        cont.0 += tune::gat_spin_hum() * p.spin;
                        let t = if rt > 0.05 || p.spin > 0.02 { tune::gat_fire(p.spin, p.heat) } else { tune::gat_idle() };
                        fx.dsx.set(R, t);
                    }
                }
            }

            // 喷气背包的扳机手感与震动
            let low = p.fuel < tune::jet_low_fuel();
            let lt_trig = if p.fuel <= 0.0 {
                tune::jet_empty()
            } else if low && inp.lt > 0.06 {
                tune::jet_sputter()
            } else {
                tune::jet(p.fuel)
            };
            fx.dsx.set(L, lt_trig);
            let sputter = if low && (p.anim * 14.0).sin() < 0.0 { 0.35 } else { 1.0 };
            cont.0 += tune::jet_hum() * p.thrust * sputter;
            fx.sfx.jet(p.thrust * sputter);

            // 低血量心跳：每秒「咚-咚」两下
            if p.hp <= 2 {
                let before = p.beat;
                p.beat -= dt;
                if p.beat <= 0.0 {
                    p.beat = 1.0;
                    fx.rum.hit(tune::heartbeat());
                } else if before >= 0.82 && p.beat < 0.82 {
                    fx.rum.hit(tune::heartbeat());
                }
            }
            fx.rum.cont = cont;
        }
        if fell {
            // 掉坑：扣一格血，放回最后站稳的位置
            let safe = self.p.safe;
            self.p.x = safe.0;
            self.p.y = safe.1 - 1.0;
            self.p.inv = 0.0;
            self.damage_player(1, safe.0, fx);
            self.p.vx = 0.0;
            self.p.vy = 0.0;
        }
    }

    fn damage_player(&mut self, dmg: i32, from_x: f32, fx: &mut Fx) {
        let p = &mut self.p;
        if p.inv > 0.0 || p.dead > 0.0 {
            return;
        }
        p.hp -= dmg;
        p.inv = 1.0;
        p.vx = if p.x + PW / 2.0 >= from_x { 120.0 } else { -120.0 };
        p.vy = -140.0;
        p.draw = 0.0;
        self.shake = self.shake.max(4.0);
        fx.rum.hit(tune::hurt());
        fx.dsx.kick_both(tune::hurt_kick(), tune::hurt_kick_time());
        fx.sfx.play(S::Hurt);
        burst(&mut self.parts, p.x + PW / 2.0, p.y + PH / 2.0, 8, pal::RED, 80.0, 0.4, 200.0);
        if p.hp <= 0 {
            p.hp = 0;
            p.dead = 1.3;
            self.stats.deaths += 1;
            burst(&mut self.parts, p.x + PW / 2.0, p.y + PH / 2.0, 24, pal::YELLOW, 130.0, 0.8, 300.0);
        }
    }

    // ───────────────────────── 敌人 ─────────────────────────

    fn update_enemies(&mut self, dt: f32, fx: &mut Fx) {
        let mut wake_say = false;
        {
            let World { en, lvl, p, pr, parts, booms, hurt_q, shake, boss_awake, stats, .. } = self;
            let (pcx, pcy) = (p.x + PW / 2.0, p.y + PH / 2.0);
            let palive = p.dead <= 0.0;
            for e in en.iter_mut() {
                if e.dead {
                    continue;
                }
                e.flash = (e.flash - dt).max(0.0);
                let (cx, cy) = (e.x + e.w / 2.0, e.y + e.h / 2.0);
                let (dx, dy) = (pcx - cx, pcy - cy);
                let dist = (dx * dx + dy * dy).sqrt();
                let active = e.group == G_ARENA || dist < 260.0;
                match e.k {
                    EK::Dummy | EK::Barrel => {}
                    EK::Slime => {
                        if !active {
                            continue;
                        }
                        e.vy = (e.vy + GRAV * dt).min(420.0);
                        e.t -= dt;
                        if e.ground && e.t <= 0.0 {
                            e.face = if dx >= 0.0 { 1.0 } else { -1.0 };
                            e.vy = -150.0 - rf(0.0, 40.0);
                            e.vx = e.face * rf(45.0, 75.0);
                            e.t = rf(0.5, 1.0);
                            e.ground = false;
                        }
                        if e.ground {
                            e.vx = approach(e.vx, 0.0, 400.0 * dt);
                        }
                        let vy = e.vy;
                        let (hx, hy) = lvl.move_rect(&mut e.x, &mut e.y, e.w, e.h, e.vx * dt, e.vy * dt);
                        if hx {
                            e.vx = -e.vx * 0.5;
                        }
                        if hy {
                            e.ground = vy > 0.0;
                            e.vy = 0.0;
                        } else {
                            e.ground = false;
                        }
                        if e.y > LH as f32 * TS + 40.0 {
                            e.hp = 0.0; // 掉坑
                        }
                    }
                    EK::Bat => {
                        if !active {
                            continue;
                        }
                        e.st_t += dt;
                        if e.t > 0.0 && e.st == 1 {
                            // 咬到人之后先飞开
                            e.t -= dt;
                            e.vx = approach(e.vx, -dx.signum() * 60.0, 300.0 * dt);
                            e.vy = approach(e.vy, -50.0, 300.0 * dt);
                        } else if dist < 190.0 {
                            e.st = 0;
                            let k = 62.0 / dist.max(1.0);
                            e.vx = approach(e.vx, dx * k, 160.0 * dt);
                            e.vy = approach(e.vy, dy * k + (e.st_t * 5.0).sin() * 25.0, 200.0 * dt);
                        } else {
                            e.vx = approach(e.vx, 0.0, 100.0 * dt);
                            e.vy = (e.st_t * 3.0).sin() * 12.0;
                        }
                        let (hx, hy) = lvl.move_rect(&mut e.x, &mut e.y, e.w, e.h, e.vx * dt, e.vy * dt);
                        if hx {
                            e.vx = -e.vx * 0.5;
                        }
                        if hy {
                            e.vy = -e.vy * 0.5;
                        }
                        e.face = if dx >= 0.0 { 1.0 } else { -1.0 };
                    }
                    EK::Turret => {
                        e.t -= dt;
                        if palive && dist < 210.0 && e.t <= 0.0 {
                            e.t = 2.2;
                            let k = 75.0 / dist.max(1.0);
                            pr.push(Proj::new(PK::Orb, cx, e.y + 2.0, dx * k, dy * k, 1.0, 4.0, false));
                            fx.sfx.play_v(S::Tick, 0.6);
                        }
                    }
                    EK::Golem => {
                        let phase2 = e.hp < e.max_hp * 0.5;
                        let near = (1.0 - dist / 260.0).clamp(0.15, 1.0);
                        match e.st {
                            G_SLEEP => {
                                e.vx = 0.0;
                                if *boss_awake {
                                    e.st = G_INTRO;
                                    e.st_t = 1.4;
                                    wake_say = true;
                                    *shake = shake.max(4.0);
                                    fx.sfx.play(S::Roar);
                                    fx.rum.hit(tune::roar());
                                    fx.dsx.kick_both(tune::roar_trig(), tune::roar_time());
                                }
                            }
                            G_INTRO => {
                                e.st_t -= dt;
                                if e.st_t <= 0.0 {
                                    e.st = G_WALK;
                                    e.st_t = rf(1.0, 1.8);
                                }
                            }
                            G_WALK => {
                                e.face = if dx >= 0.0 { 1.0 } else { -1.0 };
                                e.vx = e.face * if phase2 { 34.0 } else { 24.0 };
                                e.st_t -= dt;
                                if e.st_t <= 0.0 {
                                    let r = rf(0.0, 1.0);
                                    if dx.abs() < 64.0 || r < 0.3 {
                                        e.st = G_STOMP_TELE;
                                        e.st_t = if phase2 { 0.5 } else { 0.7 };
                                    } else if phase2 && r < 0.65 {
                                        e.st = G_CHARGE_TELE;
                                        e.st_t = 0.8;
                                    } else {
                                        e.st = G_THROW;
                                        e.st_t = 1.4;
                                        e.n = if phase2 { 4 } else { 3 };
                                        e.t = 0.35;
                                    }
                                }
                            }
                            G_STOMP_TELE => {
                                e.vx = 0.0;
                                e.st_t -= dt;
                                if e.st_t <= 0.0 {
                                    e.st = G_STOMP_REC;
                                    e.st_t = if phase2 { 0.55 } else { 0.8 };
                                    let fy = e.y + e.h - 4.0;
                                    pr.push(Proj::new(PK::Wave, cx - 16.0, fy, -140.0, 0.0, 1.0, 1.7, false));
                                    pr.push(Proj::new(PK::Wave, cx + 16.0, fy, 140.0, 0.0, 1.0, 1.7, false));
                                    *shake = shake.max(6.0);
                                    burst(parts, cx, e.y + e.h, 18, pal::GRAY, 110.0, 0.5, 200.0);
                                    fx.sfx.play(S::Stomp);
                                    fx.rum.hit(tune::stomp(near));
                                    if near > tune::shock_near() {
                                        fx.dsx.kick_both(tune::shock(), tune::shock_time());
                                    }
                                }
                            }
                            G_STOMP_REC | G_STUN => {
                                e.vx = 0.0;
                                e.st_t -= dt;
                                if e.st_t <= 0.0 {
                                    e.st = G_WALK;
                                    e.st_t = rf(1.0, 1.8);
                                }
                            }
                            G_THROW => {
                                e.vx = 0.0;
                                e.face = if dx >= 0.0 { 1.0 } else { -1.0 };
                                e.st_t -= dt;
                                e.t -= dt;
                                if e.t <= 0.0 && e.n > 0 {
                                    e.n -= 1;
                                    e.t = 0.28;
                                    // 抛物线：算好初速让石块落在玩家附近
                                    let tf = rf(0.85, 1.15);
                                    let tx = dx + rf(-14.0, 14.0);
                                    let ty = pcy - (e.y + 4.0);
                                    pr.push(Proj::new(PK::Rock, cx, e.y + 4.0, tx / tf, ty / tf - 0.5 * 700.0 * tf, 1.0, 4.0, false));
                                    fx.sfx.play_v(S::Land, 0.8);
                                }
                                if e.st_t <= 0.0 {
                                    e.st = G_WALK;
                                    e.st_t = rf(1.0, 1.8);
                                }
                            }
                            G_CHARGE_TELE => {
                                e.vx = 0.0;
                                e.face = if dx >= 0.0 { 1.0 } else { -1.0 };
                                e.st_t -= dt;
                                if e.st_t <= 0.0 {
                                    e.st = G_CHARGE;
                                    e.st_t = 1.5;
                                    fx.sfx.play_v(S::Roar, 0.6);
                                }
                            }
                            G_CHARGE => {
                                e.vx = e.face * 200.0;
                                e.st_t -= dt;
                                fx.rum.cont.0 += 0.25 * near;
                                if e.st_t <= 0.0 {
                                    e.st = G_WALK;
                                    e.st_t = rf(0.8, 1.4);
                                }
                            }
                            _ => {
                                // 崩解：持续小爆炸，结束时一次大的
                                e.vx = 0.0;
                                e.st_t -= dt;
                                fx.rum.cont.0 += 0.35;
                                fx.rum.cont.1 += 0.2;
                                *shake = shake.max(2.0);
                                if rf(0.0, 1.0) < 0.3 {
                                    burst(parts, e.x + rf(0.0, e.w), e.y + rf(0.0, e.h), 6, pal::CYAN, 90.0, 0.5, 150.0);
                                }
                                if e.st_t <= 0.0 {
                                    e.dead = true;
                                    stats.kills += 1;
                                    booms.push((cx, cy));
                                    booms.push((cx - 10.0, cy + 8.0));
                                    booms.push((cx + 10.0, cy - 8.0));
                                }
                            }
                        }
                        e.vy = (e.vy + GRAV * dt).min(420.0);
                        let (hx, hy) = lvl.move_rect(&mut e.x, &mut e.y, e.w, e.h, e.vx * dt, e.vy * dt);
                        if hy {
                            e.vy = 0.0;
                        }
                        if hx && e.st == G_CHARGE {
                            // 撞墙眩晕：这段时间伤害加成
                            e.st = G_STUN;
                            e.st_t = 1.6;
                            *shake = shake.max(6.0);
                            burst(parts, cx + e.face * 14.0, cy, 16, pal::GRAY, 120.0, 0.5, 200.0);
                            fx.sfx.play(S::Boom);
                            fx.rum.hit(tune::stomp(near));
                        }
                    }
                }
                // 接触伤害
                let touch = match e.k {
                    EK::Slime | EK::Bat => 1,
                    EK::Golem if e.st != G_SLEEP && e.st != G_DYING => {
                        if e.st == G_CHARGE {
                            2
                        } else {
                            1
                        }
                    }
                    _ => 0,
                };
                if touch > 0 && palive && p.inv <= 0.0 && overlap(e.x, e.y, e.w, e.h, p.x, p.y, PW, PH) {
                    *hurt_q = Some((touch, cx));
                    if e.k == EK::Bat {
                        e.st = 1;
                        e.t = 0.8;
                    }
                }
            }
        }
        if wake_say {
            self.say("矿洞巨像", "CAVE GOLEM");
        }
    }

    // ───────────────────────── 弹幕 ─────────────────────────

    fn update_projs(&mut self, dt: f32, fx: &mut Fx) {
        let World { pr, en, lvl, p, parts, floats, hurt_q, stats, .. } = self;
        let palive = p.dead <= 0.0;
        let (pcx, pcy) = (p.x + PW / 2.0, p.y + PH / 2.0);
        for q in pr.iter_mut() {
            if q.dead {
                continue;
            }
            q.life -= dt;
            if q.life <= 0.0 {
                q.dead = true;
                continue;
            }
            if q.stuck {
                continue;
            }
            match q.k {
                PK::Arrow => q.vy += 380.0 * dt,
                PK::Rock => q.vy += 700.0 * dt,
                _ => {}
            }
            // 分小步推进，高速子弹不会穿过薄目标
            let travel = (q.vx * q.vx + q.vy * q.vy).sqrt() * dt;
            let n = (travel / 3.0).ceil().max(1.0) as i32;
            let (sx, sy) = (q.vx * dt / n as f32, q.vy * dt / n as f32);
            'steps: for _ in 0..n {
                q.x += sx;
                q.y += sy;
                let blocked = if q.k == PK::Wave {
                    // 冲击波贴地走：撞墙或脚下没地就消散
                    lvl.solid_px(q.x, q.y) || !lvl.solid_px(q.x, q.y + 8.0)
                } else {
                    lvl.solid_px(q.x, q.y)
                };
                if blocked {
                    match q.k {
                        PK::Arrow => {
                            q.stuck = true;
                            q.life = q.life.min(2.5);
                            fx.sfx.play_v(S::ArrowHit, 0.5);
                        }
                        PK::Bullet | PK::Gat => {
                            q.dead = true;
                            burst(parts, q.x - sx, q.y - sy, 3, pal::YELLOW, 60.0, 0.2, 100.0);
                        }
                        PK::Rock => {
                            q.dead = true;
                            burst(parts, q.x, q.y - 2.0, 8, pal::ROCK_L, 80.0, 0.4, 300.0);
                            let d = ((q.x - pcx).powi(2) + (q.y - pcy).powi(2)).sqrt();
                            let near = (1.0 - d / 120.0).clamp(0.0, 1.0);
                            let h = tune::rock_land();
                            fx.rum.hit((h.0 * near, h.1 * near, h.2));
                            fx.sfx.play_v(S::Land, 0.3 + 0.7 * near);
                        }
                        _ => q.dead = true,
                    }
                    break 'steps;
                }
                if q.player {
                    for e in en.iter_mut() {
                        if e.dead || e.hp <= 0.0 || e.id == q.last_hit {
                            continue;
                        }
                        if e.k == EK::Golem && (e.st == G_SLEEP || e.st == G_DYING) {
                            continue;
                        }
                        if q.x < e.x - 1.0 || q.x > e.x + e.w + 1.0 || q.y < e.y - 1.0 || q.y > e.y + e.h + 1.0 {
                            continue;
                        }
                        let mut dmg = q.dmg;
                        let mut crit = false;
                        if e.k == EK::Golem {
                            // 胸口晶核暴击；眩晕时再加成
                            let (ccx, ccy) = (e.x + e.w / 2.0, e.y + 17.0);
                            if (q.x - ccx).abs() < 7.0 && (q.y - ccy).abs() < 7.0 {
                                dmg *= 2.0;
                                crit = true;
                            }
                            if e.st == G_STUN {
                                dmg *= 1.5;
                            }
                        }
                        e.hp -= dmg;
                        e.flash = 0.12;
                        stats.hits += 1;
                        burst(parts, q.x, q.y, 4, if crit { pal::CYAN } else { pal::WHITE }, 70.0, 0.25, 100.0);
                        if dmg >= 2.0 || crit {
                            let s = format!("{}", dmg.round() as i32);
                            floats.push(Floater { x: q.x, y: e.y - 2.0, life: 0.7, col: if crit { pal::YELLOW } else { pal::WHITE }, cn: s.clone(), en: s });
                        }
                        fx.rum.hit(tune::hit_confirm());
                        fx.sfx.play_v(S::Hit, 0.6);
                        if q.k == PK::Arrow && q.pierce > 0 {
                            q.pierce -= 1;
                            q.last_hit = e.id;
                        } else {
                            q.dead = true;
                            break 'steps;
                        }
                    }
                } else if palive {
                    let (hw, hh) = if q.k == PK::Wave { (5.0, 4.0) } else { (2.0, 2.0) };
                    if overlap(q.x - hw, q.y - hh, hw * 2.0, hh * 2.0, p.x, p.y, PW, PH) {
                        if p.inv <= 0.0 {
                            *hurt_q = Some((q.dmg as i32, q.x));
                        }
                        if q.k != PK::Wave {
                            q.dead = true;
                            break 'steps;
                        }
                    }
                }
            }
        }
        pr.retain(|q| !q.dead);
    }

    fn process_booms(&mut self, fx: &mut Fx) {
        if self.booms.is_empty() {
            return;
        }
        let list = std::mem::take(&mut self.booms);
        let (pcx, pcy) = (self.p.x + PW / 2.0, self.p.y + PH / 2.0);
        for (x, y) in list {
            burst(&mut self.parts, x, y, 22, pal::ORANGE, 150.0, 0.6, 200.0);
            burst(&mut self.parts, x, y, 12, pal::YELLOW, 90.0, 0.4, 100.0);
            burst(&mut self.parts, x, y, 10, pal::DGRAY, 50.0, 0.9, -40.0);
            self.shake = self.shake.max(5.0);
            fx.sfx.play(S::Boom);
            let d = ((x - pcx).powi(2) + (y - pcy).powi(2)).sqrt();
            let near = (1.0 - d / 170.0).clamp(0.0, 1.0);
            if near > 0.0 {
                fx.rum.hit(tune::explosion(near));
                if near > tune::shock_near() {
                    fx.dsx.kick_both(tune::shock(), tune::shock_time() * near);
                }
            }
            for e in self.en.iter_mut() {
                if e.dead || (e.k == EK::Golem && (e.st == G_SLEEP || e.st == G_DYING)) {
                    continue;
                }
                let (ex, ey) = (e.x + e.w / 2.0, e.y + e.h / 2.0);
                if ((x - ex).powi(2) + (y - ey).powi(2)).sqrt() < 46.0 {
                    e.hp -= 10.0;
                    e.flash = 0.15;
                }
            }
            if d < 38.0 && self.p.dead <= 0.0 {
                self.hurt_q = Some((2, x));
            }
        }
    }

    /// 清算血量归零的敌人
    fn reap(&mut self, fx: &mut Fx) {
        let World { en, booms, parts, stats, .. } = self;
        for e in en.iter_mut() {
            if e.dead || e.hp > 0.0 {
                continue;
            }
            let (cx, cy) = (e.x + e.w / 2.0, e.y + e.h / 2.0);
            match e.k {
                EK::Golem => {
                    if e.st != G_DYING {
                        e.st = G_DYING;
                        e.st_t = 2.8;
                        fx.sfx.play(S::Roar);
                    }
                }
                EK::Barrel => {
                    e.dead = true;
                    booms.push((cx, cy));
                }
                _ => {
                    e.dead = true;
                    stats.kills += 1;
                    let col = match e.k {
                        EK::Slime => pal::GREEN,
                        EK::Bat => pal::PURPLE,
                        EK::Turret => pal::CYAN,
                        _ => pal::BROWN,
                    };
                    burst(parts, cx, cy, 12, col, 100.0, 0.5, 250.0);
                    fx.rum.hit(tune::kill());
                    fx.sfx.play(S::Kill);
                }
            }
        }
        en.retain(|e| !e.dead);
    }

    // ───────────────────────── 关卡流程 ─────────────────────────

    fn update_world(&mut self, dt: f32, fx: &mut Fx) {
        let px = self.p.x + PW / 2.0;
        let palive = self.p.dead <= 0.0;

        // 分组清场判定
        let mut alive = [0u32; 8];
        for e in &self.en {
            if !e.dead {
                alive[e.group as usize & 7] += 1;
            }
        }
        for g in 1..8 {
            if self.started[g] && !self.done[g] && alive[g] == 0 && self.pending[g] == 0 {
                self.done[g] = true;
            }
        }

        // 闸门
        let (mut start_arena, mut wake_boss, mut opened) = (false, false, false);
        for g in self.lvl.gates.iter_mut() {
            let gi = g.group as usize & 7;
            if let Some(cx) = g.close_x {
                if !g.triggered && palive && px > cx && !self.done[gi] {
                    g.triggered = true;
                    g.closed = true;
                    if g.group == G_ARENA {
                        start_arena = true;
                    }
                    if g.group == G_BOSS {
                        wake_boss = true;
                    }
                    fx.sfx.play(S::Gate);
                    fx.rum.hit(tune::gate());
                }
            }
            if g.closed && self.done[gi] {
                g.closed = false;
                opened = true;
            }
            g.anim = approach(g.anim, if g.closed { 0.0 } else { 1.0 }, 2.5 * dt);
        }
        if opened {
            fx.sfx.play(S::Gate);
            fx.rum.hit(tune::gate());
            self.shake = self.shake.max(2.0);
        }
        if wake_boss {
            self.boss_awake = true;
        }
        if start_arena {
            self.arena = Arena { state: 1, wave: 0, left: WAVES[0], spawn_t: 0.6, gap: 0.0 };
            self.pending[G_ARENA as usize] = WAVES.iter().sum();
            self.started[G_ARENA as usize] = true;
            self.say("第 1 波", "WAVE 1");
        }

        // 竞技场刷怪：一波清完再来下一波
        if self.arena.state == 1 {
            if self.arena.left > 0 {
                self.arena.spawn_t -= dt;
                if self.arena.spawn_t <= 0.0 {
                    let left_side = self.arena.left % 2 == 0;
                    let x = if left_side { self.lvl.arena.0 + 28.0 } else { self.lvl.arena.1 - 44.0 };
                    let bat = self.arena.wave >= 1 && self.arena.left % 4 == 0;
                    if bat {
                        self.spawn(EK::Bat, x, 3.0 * TS, G_ARENA);
                    } else {
                        self.spawn(EK::Slime, x, 2.5 * TS, G_ARENA);
                    }
                    self.arena.left -= 1;
                    self.pending[G_ARENA as usize] = self.pending[G_ARENA as usize].saturating_sub(1);
                    self.arena.spawn_t = 0.55 - 0.08 * self.arena.wave as f32;
                }
            } else if alive[G_ARENA as usize] == 0 {
                if self.arena.wave + 1 < WAVES.len() {
                    self.arena.gap += dt;
                    if self.arena.gap > 1.2 {
                        self.arena.wave += 1;
                        self.arena.left = WAVES[self.arena.wave];
                        self.arena.gap = 0.0;
                        self.arena.spawn_t = 0.3;
                        let n = self.arena.wave + 1;
                        self.say(&format!("第 {} 波", n), &format!("WAVE {}", n));
                    }
                } else {
                    self.arena.state = 2;
                    self.say("清场！", "CLEAR!");
                }
            }
        }

        // 存档点：经过即激活并回满血
        let mut hit_cp = None;
        for (i, &cx) in self.lvl.checkpoints.iter().enumerate() {
            if palive && px > cx && i as i32 > self.cp_idx {
                hit_cp = Some((i as i32, cx));
            }
        }
        if let Some((i, cx)) = hit_cp {
            self.cp_idx = i;
            self.cp = (cx + 4.0, FLOOR - PH);
            self.p.hp = MAX_HP;
            fx.sfx.play(S::Check);
            fx.rum.hit(tune::checkpoint());
            self.floats.push(Floater { x: cx + 8.0, y: FLOOR - 30.0, life: 1.4, col: pal::YELLOW, cn: "存档点".into(), en: "CHECKPOINT".into() });
        }

        // 路牌：靠近时显示说明
        self.sign = None;
        for (i, s) in self.lvl.signs.iter().enumerate() {
            if (s.x - px).abs() < 30.0 {
                self.sign = Some(i);
            }
        }

        // 回血道具
        if palive {
            for h in self.lvl.hearts.iter_mut() {
                if !h.2 && overlap(h.0 - 2.0, h.1 - 2.0, 11.0, 10.0, self.p.x, self.p.y, PW, PH) {
                    h.2 = true;
                    self.p.hp = (self.p.hp + 2).min(MAX_HP);
                    fx.sfx.play(S::Pick);
                    fx.rum.hit(tune::pickup());
                    burst(&mut self.parts, h.0 + 3.0, h.1 + 3.0, 8, pal::RED, 60.0, 0.4, 0.0);
                }
            }
        }

        // 粒子 / 飘字 / 横幅 / 震屏
        for q in self.parts.iter_mut() {
            q.life -= dt;
            q.vy += q.grav * dt;
            q.x += q.vx * dt;
            q.y += q.vy * dt;
        }
        self.parts.retain(|q| q.life > 0.0);
        for f in self.floats.iter_mut() {
            f.life -= dt;
            f.y -= 18.0 * dt;
        }
        self.floats.retain(|f| f.life > 0.0);
        self.banner.2 = (self.banner.2 - dt).max(0.0);
        self.shake = (self.shake - 18.0 * dt).max(0.0);

        // 通关：巨像倒下后稍等片刻
        if self.done[G_BOSS as usize] {
            self.win_t += dt;
            if self.win_t > 1.6 && !self.won {
                self.won = true;
                fx.dsx.relax();
                fx.sfx.jet(0.0);
                fx.sfx.play(S::Win);
            }
        }
    }

    fn update_cam(&mut self, dt: f32) {
        let mut target = self.p.x + PW / 2.0 - VW / 2.0 + self.p.face * 24.0;
        let (mut lo, mut hi) = (0.0, LW as f32 * TS - VW);
        // 遭遇战期间镜头锁在场内
        if self.arena.state == 1 {
            lo = self.lvl.arena.0;
            hi = self.lvl.arena.1 - VW;
        }
        if self.boss_awake && !self.done[G_BOSS as usize] {
            lo = self.lvl.boss.0;
            hi = self.lvl.boss.1 - VW;
        }
        target = target.clamp(lo, hi.max(lo));
        self.cam += (target - self.cam) * (8.0 * dt).min(1.0);
    }

    // ───────────────────────── 绘制 ─────────────────────────

    pub fn draw(&self, g: &mut Gfx, hud: &Hud) {
        let (sx, sy) = if self.shake > 0.3 {
            (rf(-self.shake, self.shake).round(), rf(-self.shake, self.shake).round())
        } else {
            (0.0, 0.0)
        };
        let cam = self.cam.floor();
        // 地图高 176 像素，画布 180：上下各留 2 像素
        let (ox, oy) = (-cam + sx, 2.0 + sy);
        draw_backdrop(self.t, cam);
        self.draw_tiles(cam, ox, oy);
        self.draw_props(g, ox, oy);
        self.draw_enemies(g, ox, oy);
        self.draw_player(g, ox, oy);
        self.draw_projs(ox, oy);
        for q in &self.parts {
            rect_a(q.x + ox, q.y + oy, q.size, q.size, q.col, (q.life / q.max).clamp(0.0, 1.0));
        }
        for f in &self.floats {
            let s = if g.cn { f.cn.clone() } else { f.en.clone() };
            g.text_ca(f.x + ox, f.y + oy, 6.0, f.col, (f.life * 3.0).min(1.0), &s);
        }
        self.draw_hud(g, hud);
    }

    fn draw_tiles(&self, cam: f32, ox: f32, oy: f32) {
        let tx0 = (cam / TS).floor() as i32 - 1;
        let tx1 = tx0 + (VW / TS) as i32 + 3;
        let lh = LH as i32;
        for ty in -1..=lh {
            for tx in tx0..=tx1 {
                // 画布比地图高一点：最下面多画一行，沿用末行的地形
                let t = self.lvl.get(tx, ty.min(lh - 1));
                if t == Tile::Empty {
                    continue;
                }
                let (x, y) = (tx as f32 * TS + ox, ty as f32 * TS + oy);
                let h = hash((tx as u32).wrapping_mul(7919).wrapping_add((ty as u32).wrapping_mul(104_729)));
                match t {
                    Tile::Rock => {
                        rect(x, y, TS, TS, pal::ROCK);
                        rect(x + (h % 12) as f32, y + ((h >> 4) % 12) as f32, 3.0, 2.0, pal::ROCK_D);
                        rect(x + ((h >> 8) % 13) as f32, y + ((h >> 12) % 13) as f32, 2.0, 2.0, pal::ROCK_D);
                        rect(x + ((h >> 16) % 14) as f32, y + ((h >> 20) % 14) as f32, 1.0, 1.0, pal::ROCK_L);
                        if ty >= 1 && ty < lh && self.lvl.get(tx, ty - 1) == Tile::Empty {
                            // 顶面长苔
                            rect(x, y, TS, 2.0, pal::DGREEN);
                            rect(x, y, TS, 1.0, pal::GREEN);
                            rect(x + ((h >> 24) % 13) as f32, y - 1.0, 2.0, 1.0, pal::GREEN);
                        }
                        if ty < lh - 1 && self.lvl.get(tx, ty + 1) == Tile::Empty {
                            rect(x, y + TS - 2.0, TS, 2.0, pal::ROCK_D);
                        }
                        if self.lvl.get(tx - 1, ty) == Tile::Empty && ty < lh {
                            rect(x, y, 1.0, TS, pal::ROCK_L);
                        }
                        if self.lvl.get(tx + 1, ty) == Tile::Empty && ty < lh {
                            rect(x + TS - 1.0, y, 1.0, TS, pal::ROCK_D);
                        }
                    }
                    Tile::Wood => {
                        rect(x, y, TS, TS, pal::BROWN);
                        rect(x, y, TS, 2.0, 0xd9a066);
                        rect(x, y + 7.0, TS, 1.0, pal::DBROWN);
                        rect(x, y + 15.0, TS, 1.0, pal::DBROWN);
                        rect(x + 7.0, y + 2.0, 1.0, 5.0, pal::DBROWN);
                        rect(x + 3.0, y + 8.0, 1.0, 7.0, pal::DBROWN);
                        rect(x + 11.0, y + 8.0, 1.0, 7.0, pal::DBROWN);
                    }
                    Tile::Empty => {}
                }
            }
        }
    }

    fn draw_props(&self, g: &mut Gfx, ox: f32, oy: f32) {
        let floor = FLOOR + oy;
        // 路牌
        for (i, s) in self.lvl.signs.iter().enumerate() {
            let x = s.x + ox;
            if x < -20.0 || x > VW + 20.0 {
                continue;
            }
            rect(x - 1.0, floor - 10.0, 2.0, 10.0, pal::DBROWN);
            rect(x - 6.0, floor - 19.0, 12.0, 10.0, pal::BROWN);
            rect(x - 6.0, floor - 19.0, 12.0, 1.0, 0xd9a066);
            rect(x - 1.0, floor - 17.0, 2.0, 4.0, pal::INK);
            rect(x - 1.0, floor - 12.0, 2.0, 1.0, pal::INK);
            if self.sign == Some(i) {
                let bob = (self.t * 5.0).sin().round();
                rect(x - 1.0, floor - 25.0 + bob, 2.0, 2.0, pal::YELLOW);
            }
        }
        // 存档灯
        for (i, &cx) in self.lvl.checkpoints.iter().enumerate() {
            let x = cx + ox;
            if x < -20.0 || x > VW + 20.0 {
                continue;
            }
            let lit = i as i32 <= self.cp_idx;
            rect(x + 7.0, floor - 20.0, 2.0, 20.0, pal::DGRAY);
            rect(x + 4.0, floor - 27.0, 8.0, 8.0, pal::INK);
            rect(x + 5.0, floor - 26.0, 6.0, 6.0, if lit { pal::YELLOW } else { pal::DGRAY });
            if lit {
                let a = 0.12 + 0.06 * (self.t * 4.0).sin();
                rect_a(x - 1.0, floor - 32.0, 18.0, 18.0, pal::YELLOW, a);
            }
        }
        // 闸门：落下时从洞顶垂到地面
        for gate in &self.lvl.gates {
            let x = gate.tx as f32 * TS + ox;
            if x < -20.0 || x > VW + 20.0 {
                continue;
            }
            let hgt = ((1.0 - gate.anim) * 8.0 * TS).round();
            if hgt < 1.0 {
                continue;
            }
            let top = TS + oy;
            rect(x + 3.0, top, 10.0, hgt, pal::DGRAY);
            rect(x + 3.0, top, 2.0, hgt, pal::GRAY);
            rect(x + 11.0, top, 2.0, hgt, pal::INK);
            let mut k = 6.0;
            while k < hgt {
                rect(x + 3.0, top + k, 10.0, 1.0, pal::INK);
                k += 8.0;
            }
        }
        // 回血道具
        for h in &self.lvl.hearts {
            if !h.2 {
                let bob = (self.t * 3.0 + h.0).sin() * 1.5;
                spr(&g.s.heart, h.0 + ox, h.1 + oy + bob, false, WHITE);
            }
        }
    }

    fn draw_enemies(&self, g: &mut Gfx, ox: f32, oy: f32) {
        for e in &self.en {
            let (x, y) = (e.x + ox, e.y + oy);
            if x < -40.0 || x > VW + 40.0 {
                continue;
            }
            let tint = if e.flash > 0.0 { rgb(0xff8a8a) } else { WHITE };
            match e.k {
                EK::Dummy => spr(&g.s.dummy, x, y, false, tint),
                EK::Barrel => spr(&g.s.barrel, x, y, false, tint),
                EK::Turret => spr(&g.s.turret, x, y, false, tint),
                EK::Slime => {
                    let f = if e.ground { 1 } else { 0 };
                    spr(&g.s.slime[f], x, y - 1.0, e.face < 0.0, tint);
                }
                EK::Bat => {
                    let f = ((self.t * 9.0 + e.id as f32) as usize) % 2;
                    spr(&g.s.bat[f], x, y - 1.0, e.face < 0.0, tint);
                }
                EK::Golem => self.draw_golem(e, x, y),
            }
        }
    }

    fn draw_golem(&self, e: &Enemy, x0: f32, y0: f32) {
        let mut x = x0;
        let mut y = y0;
        let hit = e.flash > 0.0;
        let body = if hit { pal::WHITE } else { pal::GRAY };
        let dark = if hit { pal::GRAY } else { pal::DGRAY };
        let mut eye = pal::CYAN;
        let mut leg_l = 0.0;
        match e.st {
            G_SLEEP => eye = pal::DGRAY,
            G_STOMP_TELE => {
                // 抬脚蓄力：一条腿抬起，身体发抖
                leg_l = -6.0;
                x += rf(-1.0, 1.0).round();
            }
            G_CHARGE_TELE | G_CHARGE => {
                eye = pal::RED;
                x += rf(-1.0, 1.0).round();
            }
            G_STUN => eye = pal::YELLOW,
            G_DYING => {
                x += rf(-2.0, 2.0).round();
                y += rf(-1.0, 1.0).round();
                eye = pal::RED;
            }
            _ => {}
        }
        if e.st == G_WALK {
            leg_l = if (self.t * 4.0).sin() > 0.0 { -2.0 } else { 0.0 };
        }
        // 腿
        rect(x + 2.0, y + 24.0 + leg_l, 9.0, 10.0, dark);
        rect(x + 17.0, y + 24.0 - if e.st == G_WALK { leg_l + 2.0 } else { 0.0 }, 9.0, 10.0, dark);
        // 手臂
        rect(x - 3.0, y + 10.0, 5.0, 14.0, dark);
        rect(x + 26.0, y + 10.0, 5.0, 14.0, dark);
        // 躯干 + 头
        rect(x + 1.0, y + 8.0, 26.0, 18.0, body);
        rect(x + 1.0, y + 22.0, 26.0, 4.0, dark);
        rect(x + 8.0, y, 12.0, 9.0, body);
        rect(x + 8.0, y, 12.0, 2.0, dark);
        let ex = if e.face > 0.0 { 13.0 } else { 9.0 };
        rect(x + ex, y + 4.0, 2.0, 2.0, eye);
        rect(x + ex + 4.0, y + 4.0, 2.0, 2.0, eye);
        // 胸口晶核（弱点）
        rect(x + 10.0, y + 13.0, 8.0, 8.0, pal::INK);
        let pulse = 0.55 + 0.45 * (self.t * 6.0).sin();
        let core = if e.st == G_SLEEP { pal::DGRAY } else { pal::CYAN };
        rect_a(x + 11.0, y + 14.0, 6.0, 6.0, core, pulse);
        rect(x + 13.0, y + 16.0, 2.0, 2.0, pal::WHITE);
    }

    fn draw_player(&self, g: &mut Gfx, ox: f32, oy: f32) {
        let p = &self.p;
        if p.dead > 0.0 {
            return;
        }
        if p.inv > 0.0 && ((p.inv * 16.0) as i32) % 2 == 0 {
            return; // 无敌帧闪烁
        }
        // 精灵 10x14，碰撞盒 8x13
        let frame = if !p.ground {
            3
        } else if p.vx.abs() > 12.0 {
            1 + ((p.anim * 10.0) as usize % 2)
        } else {
            0
        };
        spr(&g.s.player[frame], p.x + ox - 1.0, p.y + oy - 1.0, p.face < 0.0, WHITE);

        let (dx, dy) = (p.aim.cos() * p.face, p.aim.sin());
        let (hx, hy) = (p.x + PW / 2.0 + p.face * 2.0 + ox, p.y + 7.0 + oy);
        let (mwx, mwy, _, _) = p.muzzle(&self.lvl);
        let (mx, my) = (mwx + ox, mwy + oy);
        match p.weapon {
            Weapon::Bow => {
                let (nx, ny) = (-dy, dx);
                let (bx, by) = (hx + dx * 4.0, hy + dy * 4.0);
                let (ax, ay) = (bx + nx * 5.0, by + ny * 5.0);
                let (cx, cy) = (bx - nx * 5.0, by - ny * 5.0);
                let (tx, ty) = (bx + dx * 2.0, by + dy * 2.0);
                draw_line(ax, ay, tx, ty, 1.0, rgb(pal::BROWN));
                draw_line(cx, cy, tx, ty, 1.0, rgb(pal::BROWN));
                let (sx, sy) = (bx - dx * p.draw * 4.0, by - dy * p.draw * 4.0);
                let string = if p.draw >= 0.97 { pal::YELLOW } else { pal::WHITE };
                draw_line(ax, ay, sx, sy, 1.0, rgba(string, 0.85));
                draw_line(cx, cy, sx, sy, 1.0, rgba(string, 0.85));
                if p.draw > 0.05 {
                    draw_line(sx, sy, sx + dx * 9.0, sy + dy * 9.0, 1.0, rgb(pal::GRAY));
                    // 弹道预览
                    let sp = 170.0 + 290.0 * p.draw;
                    for k in 1..=12 {
                        let t = k as f32 * 0.05;
                        let (wx, wy) = (mwx + dx * sp * t, mwy + dy * sp * t + 0.5 * 380.0 * t * t);
                        if self.lvl.solid_px(wx, wy) {
                            break;
                        }
                        rect_a(wx + ox, wy + oy, 1.0, 1.0, pal::WHITE, 0.7 - k as f32 * 0.045);
                    }
                }
            }
            Weapon::Revolver => {
                draw_line(hx, hy, hx + dx * 6.0, hy + dy * 6.0, 2.0, rgb(pal::GRAY));
                rect(hx - 1.0, hy, 2.0, 3.0, pal::DBROWN);
                if p.aiming {
                    // 激光瞄准线：打到墙为止
                    let mut k = 0.0;
                    while k < 220.0 {
                        let (wx, wy) = (mwx + dx * k, mwy + dy * k);
                        if self.lvl.solid_px(wx, wy) {
                            break;
                        }
                        if (k as i32 / 3) % 2 == 0 {
                            rect_a(wx + ox, wy + oy, 1.0, 1.0, pal::RED, 0.75);
                        }
                        k += 1.5;
                    }
                }
                if p.ammo == 0 && p.reload <= 0.0 && (self.t * 4.0).sin() > 0.0 {
                    let s = g.t("X 装弹", "X: RELOAD").to_string();
                    g.text_c(p.x + PW / 2.0 + ox, p.y + oy - 5.0, 6.0, pal::YELLOW, &s);
                }
            }
            Weapon::Gatling => {
                draw_line(hx, hy, hx + dx * 10.0, hy + dy * 10.0, 3.0, rgb(pal::DGRAY));
                draw_line(hx + dx * 7.0, hy + dy * 7.0, hx + dx * 10.0, hy + dy * 10.0, 3.0, mix(pal::DGRAY, pal::ORANGE, p.heat));
                rect(hx - 1.0, hy + 1.0, 3.0, 3.0, pal::INK);
                if p.over && (self.t * 6.0).sin() > 0.0 {
                    let s = g.t("过热！", "OVERHEAT!").to_string();
                    g.text_c(p.x + PW / 2.0 + ox, p.y + oy - 5.0, 6.0, pal::RED, &s);
                }
            }
        }
        if p.flash > 0.0 {
            draw_circle(mx, my, 2.5, rgb(pal::YELLOW));
        }
    }

    fn draw_projs(&self, ox: f32, oy: f32) {
        for q in &self.pr {
            let (x, y) = (q.x + ox, q.y + oy);
            if x < -20.0 || x > VW + 20.0 {
                continue;
            }
            let len = (q.vx * q.vx + q.vy * q.vy).sqrt().max(1.0);
            let (ux, uy) = (q.vx / len, q.vy / len);
            match q.k {
                PK::Arrow => {
                    let a = if q.stuck { q.life.min(1.0) } else { 1.0 };
                    draw_line(x - ux * 8.0, y - uy * 8.0, x, y, 1.0, rgba(pal::BROWN, a));
                    rect_a(x - 0.5, y - 0.5, 1.0, 1.0, pal::WHITE, a);
                }
                PK::Bullet => draw_line(x - ux * 6.0, y - uy * 6.0, x, y, 1.0, rgb(pal::YELLOW)),
                PK::Gat => draw_line(x - ux * 3.0, y - uy * 3.0, x, y, 1.0, rgb(pal::ORANGE)),
                PK::Orb => {
                    draw_circle(x, y, 3.0, rgb(pal::PURPLE));
                    draw_circle(x, y, 1.5, rgb(pal::WHITE));
                }
                PK::Rock => {
                    rect(x - 3.0, y - 3.0, 6.0, 6.0, pal::ROCK_L);
                    rect(x - 3.0, y + 1.0, 6.0, 2.0, pal::ROCK_D);
                }
                PK::Wave => {
                    let a = (q.life * 2.0).min(1.0);
                    rect_a(x - 5.0, y - 1.0, 3.0, 5.0, pal::GRAY, a);
                    rect_a(x - 1.0, y - 5.0, 3.0, 9.0, pal::WHITE, a);
                    rect_a(x + 3.0, y - 2.0, 3.0, 6.0, pal::GRAY, a);
                }
            }
        }
    }

    fn draw_hud(&self, g: &mut Gfx, hud: &Hud) {
        let p = &self.p;
        // 血量 + 燃料
        for i in 0..MAX_HP {
            let x = 4.0 + i as f32 * 7.0;
            rect(x - 1.0, 3.0, 7.0, 7.0, pal::INK);
            rect(x, 4.0, 5.0, 5.0, if i < p.hp { pal::RED } else { 0x3a2a3a });
        }
        let fuel_col = if p.fuel < tune::jet_low_fuel() { pal::RED } else { pal::ORANGE };
        bar(4.0, 13.0, 40.0, 2.0, p.fuel, fuel_col);

        // 当前武器
        let (name, gauge, col) = match p.weapon {
            Weapon::Bow => (g.t("弓", "BOW"), p.draw, if p.draw >= 0.97 { pal::WHITE } else { pal::YELLOW }),
            Weapon::Revolver => (
                g.t("左轮", "REVOLVER"),
                if p.reload > 0.0 { 1.0 - p.reload / tune::rev_reload_time() } else { p.ammo as f32 / 6.0 },
                if p.reload > 0.0 { pal::GRAY } else { pal::YELLOW },
            ),
            Weapon::Gatling => (g.t("加特林", "GATLING"), p.heat, if p.over { pal::RED } else { pal::ORANGE }),
        };
        let name = name.to_string();
        g.text_r(VW - 4.0, 9.0, 7.0, pal::WHITE, &name);
        bar(VW - 44.0, 13.0, 40.0, 2.0, gauge, col);

        // Boss 血条
        if self.boss_awake && !self.done[G_BOSS as usize] {
            if let Some(e) = self.en.iter().find(|e| e.k == EK::Golem) {
                bar(90.0, 6.0, 140.0, 3.0, (e.hp / e.max_hp).max(0.0), pal::CYAN);
            }
        }

        // 扳机面板：两侧各一块，显示按压深度 + 当前手感
        for side in 0..2 {
            let x = if side == L { 4.0 } else { VW - 66.0 };
            let v = if side == L { hud.lt } else { hud.rt };
            let t = hud.trig[side];
            rect_a(x - 2.0, VH - 21.0, 64.0, 19.0, pal::INK, 0.7);
            bar(x + 14.0, VH - 16.0, 44.0, 3.0, v, if t.mode == 4 { pal::RED } else { pal::CYAN });
            g.text(x, VH - 12.5, 6.0, pal::GRAY, if side == L { "LT" } else { "RT" });
            g.text(x, VH - 4.5, 6.0, pal::YELLOW, t.name(g.cn));
        }

        // 路牌说明
        if let Some(i) = self.sign {
            let s = &self.lvl.signs[i];
            let txt = if g.cn { s.cn } else { s.en };
            rect_a(14.0, 22.0, VW - 28.0, 30.0, pal::INK, 0.82);
            rect(14.0, 22.0, VW - 28.0, 1.0, pal::BROWN);
            for (k, line) in txt.lines().enumerate() {
                g.text_c(VW / 2.0, 34.0 + k as f32 * 11.0, 6.5, pal::WHITE, line);
            }
        }

        // 横幅
        if self.banner.2 > 0.0 {
            let s = if g.cn { self.banner.0.clone() } else { self.banner.1.clone() };
            g.text_ca(VW / 2.0, 78.0, 16.0, pal::YELLOW, self.banner.2.min(1.0), &s);
        }

        // 手感面板（Back / F1 切换）：把正在发给手柄的原始数值亮出来
        if hud.detail {
            rect_a(72.0, VH - 44.0, 176.0, 42.0, pal::INK, 0.85);
            let l1 = format!(
                "DSX 127.0.0.1:{}{}  {} {}   {} x{}",
                hud.port,
                if hud.port_found { "" } else { "*" },
                g.t("包", "pkts"),
                hud.packets,
                g.t("手柄", "pads"),
                hud.pads
            );
            g.text(76.0, VH - 37.0, 5.0, pal::GRAY, &l1);
            let l2 = format!("LT {:<9} {}", hud.trig[L].name(false), hud.trig[L].params());
            let l3 = format!("RT {:<9} {}", hud.trig[R].name(false), hud.trig[R].params());
            g.text(76.0, VH - 30.0, 5.0, pal::CYAN, &l2);
            g.text(76.0, VH - 23.0, 5.0, pal::CYAN, &l3);
            let lo = g.t("低频", "LOW").to_string();
            let hi = g.t("高频", "HIGH").to_string();
            g.text(76.0, VH - 13.0, 5.0, pal::GRAY, &lo);
            bar(96.0, VH - 16.5, 56.0, 3.0, hud.rum.0, pal::ORANGE);
            g.text(160.0, VH - 13.0, 5.0, pal::GRAY, &hi);
            bar(180.0, VH - 16.5, 56.0, 3.0, hud.rum.1, pal::YELLOW);
            if !hud.port_found {
                let s = g.t("* 没找到工具的端口文件，按默认端口发送", "* tool port file not found, using default").to_string();
                g.text(76.0, VH - 6.0, 4.5, pal::DGRAY, &s);
            }
        }
    }

    /// 通关画面用
    pub fn accuracy(&self) -> u32 {
        if self.stats.shots == 0 {
            0
        } else {
            (self.stats.hits * 100 / self.stats.shots).min(100)
        }
    }
}

/// 洞穴背景：渐变 + 两层视差（标题画面也用）
pub fn draw_backdrop(t: f32, cam: f32) {
    for i in 0..6 {
        let c = mix(pal::BG_TOP, pal::BG_BOT, i as f32 / 5.0);
        draw_rectangle(0.0, i as f32 * 30.0, VW, 30.0, c);
    }
    // 远景：钟乳石与石笋
    for i in 0..12u32 {
        let h = hash(i * 31 + 7);
        let x = (i as f32 * 61.0 - cam * 0.2).rem_euclid(VW + 80.0) - 40.0;
        let len = 14.0 + (h % 30) as f32;
        rect(x, 0.0, 10.0, len * 0.5, pal::BG_FAR);
        rect(x + 2.0, len * 0.5, 6.0, len * 0.3, pal::BG_FAR);
        rect(x + 4.0, len * 0.8, 2.0, len * 0.2, pal::BG_FAR);
        let len2 = 10.0 + ((h >> 8) % 24) as f32;
        rect(x + 30.0, VH - len2 * 0.5, 10.0, len2 * 0.5, pal::BG_FAR);
        rect(x + 32.0, VH - len2 * 0.8, 6.0, len2 * 0.3, pal::BG_FAR);
        rect(x + 34.0, VH - len2, 2.0, len2 * 0.2, pal::BG_FAR);
    }
    // 中景：石柱和一闪一闪的晶体
    for i in 0..7u32 {
        let h = hash(i * 97 + 3);
        let x = (i as f32 * 113.0 - cam * 0.45).rem_euclid(VW + 120.0) - 60.0;
        let w = 14.0 + (h % 10) as f32;
        rect(x, 0.0, w, VH, pal::BG_MID);
        rect(x, 0.0, 1.0, VH, 0x2d2350);
        let cy = 40.0 + ((h >> 8) % 90) as f32;
        let tw = (t * 2.0 + i as f32 * 1.7).sin() * 0.5 + 0.5;
        rect_a(x + 4.0, cy, 3.0, 5.0, pal::CYAN, 0.2 + 0.4 * tw);
        rect_a(x + 5.0, cy - 2.0, 1.0, 2.0, pal::CYAN, 0.2 + 0.4 * tw);
    }
}
