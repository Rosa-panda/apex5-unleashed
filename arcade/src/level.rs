//! 关卡：一张 200x11 格的横版地图，分五段，每段教一种扳机手感。
//! 地形用代码搭（`Level::build`），坐标单位是格（16 像素）。
pub const TS: f32 = 16.0;
pub const LW: usize = 200;
pub const LH: usize = 11;

/// 关卡分组：一组敌人清完，对应的闸门打开
pub const G_BOW: u8 = 1;
pub const G_REV: u8 = 2;
pub const G_ARENA: u8 = 3;
pub const G_BOSS: u8 = 4;

#[derive(Clone, Copy, PartialEq)]
pub enum Tile {
    Empty,
    Rock,
    Wood,
}

#[derive(Clone, Copy, PartialEq)]
pub enum EK {
    Dummy,
    Slime,
    Bat,
    Turret,
    Barrel,
    Golem,
}

pub struct Spawn {
    pub k: EK,
    /// 站在哪一格里（脚踩该格底边）
    pub tx: i32,
    pub ty: i32,
    pub group: u8,
}

pub struct Gate {
    pub tx: i32,
    pub group: u8,
    pub closed: bool,
    /// Some(x)：入口闸门，玩家越过 x 后才在身后落下；None：出口闸门，一开始就关着
    pub close_x: Option<f32>,
    pub triggered: bool,
    /// 0 = 完全落下，1 = 完全升起（只影响画面）
    pub anim: f32,
}

pub struct Sign {
    pub x: f32,
    pub cn: &'static str,
    pub en: &'static str,
}

pub struct Level {
    tiles: Vec<Tile>,
    pub spawns: Vec<Spawn>,
    pub gates: Vec<Gate>,
    pub signs: Vec<Sign>,
    /// 存档点的像素 x
    pub checkpoints: Vec<f32>,
    /// 回血道具（像素坐标, 是否已拾取）
    pub hearts: Vec<(f32, f32, bool)>,
    pub start: (f32, f32),
    /// 竞技场 / Boss 房的像素 x 范围（镜头锁定用）
    pub arena: (f32, f32),
    pub boss: (f32, f32),
}

impl Level {
    fn fill(&mut self, x0: i32, x1: i32, y0: i32, y1: i32, t: Tile) {
        for y in y0..=y1 {
            for x in x0..=x1 {
                if x >= 0 && y >= 0 && (x as usize) < LW && (y as usize) < LH {
                    self.tiles[y as usize * LW + x as usize] = t;
                }
            }
        }
    }

    fn spawn(&mut self, k: EK, tx: i32, ty: i32, group: u8) {
        self.spawns.push(Spawn { k, tx, ty, group });
    }

    fn gate(&mut self, tx: i32, group: u8, close_x: Option<f32>) {
        self.gates.push(Gate { tx, group, closed: close_x.is_none(), close_x, triggered: false, anim: 0.0 });
    }

    fn sign(&mut self, tx: i32, cn: &'static str, en: &'static str) {
        self.signs.push(Sign { x: tx as f32 * TS + 8.0, cn, en });
    }

    pub fn build() -> Level {
        let mut l = Level {
            tiles: vec![Tile::Empty; LW * LH],
            spawns: Vec::new(),
            gates: Vec::new(),
            signs: Vec::new(),
            checkpoints: Vec::new(),
            hearts: Vec::new(),
            start: (3.0 * TS, 9.0 * TS - 13.0),
            arena: (127.0 * TS, 154.0 * TS),
            boss: (170.0 * TS, 200.0 * TS),
        };
        let w = LW as i32;
        l.fill(0, w - 1, 0, 0, Tile::Rock); // 洞顶
        l.fill(0, w - 1, 9, 10, Tile::Rock); // 地面
        l.fill(0, 0, 1, 8, Tile::Rock);
        l.fill(w - 1, w - 1, 1, 8, Tile::Rock);

        // ── 第 1 段：营地 + 弓 ──
        l.sign(
            5,
            "左摇杆移动 · A 跳跃 · LB/RB 切换武器 · Back 看手感面板\n这是一个演示：每把武器的扳机手感都不一样",
            "Stick: move · A: jump · LB/RB: switch weapon · Back: feel panel\nA demo: every weapon makes the trigger feel different",
        );
        l.sign(
            10,
            "【弓】慢慢扣下 RT 拉弓：越拉越紧，拉满时弓弦会颤\n松开 RT 放箭，上推摇杆抬高角度。射掉 3 个靶子开门",
            "[BOW] Squeeze RT to draw: it gets tighter, and trembles at full draw\nRelease RT to shoot, push the stick up to aim higher. Break 3 targets",
        );
        l.spawn(EK::Dummy, 16, 8, G_BOW);
        l.fill(21, 23, 6, 6, Tile::Wood);
        l.spawn(EK::Dummy, 22, 5, G_BOW);
        l.fill(27, 29, 4, 4, Tile::Wood);
        l.spawn(EK::Dummy, 28, 3, G_BOW);
        l.gate(33, G_BOW, None);

        // ── 第 2 段：矿井 + 喷气背包 ──
        l.checkpoints.push(36.0 * TS);
        l.sign(
            38,
            "【喷气背包】按住 LT 起飞，按得越深推力越大\n燃料见底时扳机发抖，烧光了扳机变软。落地回油",
            "[JETPACK] Hold LT to fly, deeper press = more thrust\nThe trigger sputters when fuel is low and goes limp when empty",
        );
        l.fill(44, 50, 9, 10, Tile::Empty);
        l.fill(56, 57, 4, 8, Tile::Rock);
        l.spawn(EK::Bat, 61, 4, 0);
        l.fill(64, 75, 9, 10, Tile::Empty);
        l.fill(69, 70, 7, 7, Tile::Wood);
        l.hearts.push((69.0 * TS + 12.0, 6.0 * TS + 6.0, false));
        l.spawn(EK::Bat, 72, 3, 0);

        // ── 第 3 段：长廊 + 左轮 ──
        l.checkpoints.push(80.0 * TS);
        l.sign(
            82,
            "【左轮】RB 切到左轮。RT 半程有一道坎：停在坎前是瞄准\n用力压过去才击发。打空后扳机变软，X 装弹时扳机锁死",
            "[REVOLVER] RB to switch. RT has a wall halfway: rest on it to aim\nPush through to fire. Empty = limp trigger, X reloads (trigger locks)",
        );
        l.spawn(EK::Bat, 91, 5, G_REV);
        l.spawn(EK::Bat, 97, 3, G_REV);
        l.fill(100, 100, 8, 8, Tile::Rock);
        l.spawn(EK::Bat, 104, 5, G_REV);
        l.fill(109, 109, 6, 8, Tile::Rock);
        l.spawn(EK::Turret, 109, 5, G_REV);
        l.gate(113, G_REV, None);

        // ── 第 4 段：竞技场 + 加特林 ──
        l.checkpoints.push(117.0 * TS);
        l.sign(
            119,
            "【加特林】按住 RT 扫射，扳机跟着射速震动\n过热会把扳机锁死，松手冷却。打爆油桶可以清场",
            "[GATLING] Hold RT to spray, the trigger buzzes with the fire rate\nOverheat locks the trigger. Shoot the barrels to clear the room",
        );
        l.gate(126, G_ARENA, Some(129.0 * TS));
        l.spawn(EK::Barrel, 136, 8, 0);
        l.spawn(EK::Barrel, 145, 8, 0);
        l.gate(153, G_ARENA, None);

        // ── 第 5 段：巨像 ──
        l.checkpoints.push(157.0 * TS);
        l.hearts.push((160.0 * TS + 4.0, 8.0 * TS + 6.0, false));
        l.sign(
            162,
            "【矿洞巨像】胸口的晶核是弱点，满弓和左轮伤害最高\n它抬脚时准备起跳，躲开贴地的冲击波",
            "[CAVE GOLEM] The chest core is its weak spot: full-draw arrows and revolver hit hardest\nJump when it raises a foot to dodge the ground shockwave",
        );
        l.gate(169, G_BOSS, Some(172.0 * TS));
        l.spawn(EK::Golem, 190, 8, G_BOSS);
        l
    }

    pub fn get(&self, tx: i32, ty: i32) -> Tile {
        if tx < 0 || tx >= LW as i32 || ty < 0 {
            return Tile::Rock;
        }
        if ty >= LH as i32 {
            return Tile::Empty; // 坑底敞开：掉下去
        }
        self.tiles[ty as usize * LW + tx as usize]
    }

    /// 该格是否挡路（岩石 / 木板 / 落下的闸门）
    pub fn solid(&self, tx: i32, ty: i32) -> bool {
        if self.get(tx, ty) != Tile::Empty {
            return true;
        }
        (1..=8).contains(&ty) && self.gates.iter().any(|g| g.closed && g.tx == tx)
    }

    pub fn solid_px(&self, x: f32, y: f32) -> bool {
        self.solid((x / TS).floor() as i32, (y / TS).floor() as i32)
    }

    pub fn rect_hits(&self, x: f32, y: f32, w: f32, h: f32) -> bool {
        let x0 = (x / TS).floor() as i32;
        let x1 = ((x + w - 0.01) / TS).floor() as i32;
        let y0 = (y / TS).floor() as i32;
        let y1 = ((y + h - 0.01) / TS).floor() as i32;
        for ty in y0..=y1 {
            for tx in x0..=x1 {
                if self.solid(tx, ty) {
                    return true;
                }
            }
        }
        false
    }

    /// 单轴小步推进；撞上就停在贴墙位置。返回是否被挡。
    fn slide(&self, x: &mut f32, y: &mut f32, w: f32, h: f32, d: f32, horizontal: bool) -> bool {
        if d == 0.0 {
            return false;
        }
        let n = (d.abs() / 2.0).ceil().max(1.0) as i32;
        let step = d / n as f32;
        for _ in 0..n {
            let (nx, ny) = if horizontal { (*x + step, *y) } else { (*x, *y + step) };
            if self.rect_hits(nx, ny, w, h) {
                // 剩下不足一步的缝隙，用 1/4 像素贴上去
                let fine = 0.25 * d.signum();
                for _ in 0..8 {
                    let (fx, fy) = if horizontal { (*x + fine, *y) } else { (*x, *y + fine) };
                    if self.rect_hits(fx, fy, w, h) {
                        break;
                    }
                    *x = fx;
                    *y = fy;
                }
                return true;
            }
            *x = nx;
            *y = ny;
        }
        false
    }

    /// 带碰撞地移动一个矩形，返回（横向被挡, 纵向被挡）
    pub fn move_rect(&self, x: &mut f32, y: &mut f32, w: f32, h: f32, dx: f32, dy: f32) -> (bool, bool) {
        let hx = self.slide(x, y, w, h, dx, true);
        let hy = self.slide(x, y, w, h, dy, false);
        (hx, hy)
    }
}
