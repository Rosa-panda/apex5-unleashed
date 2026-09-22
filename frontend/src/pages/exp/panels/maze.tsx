// 体感试玩场 · 弹珠迷宫（原 #17，ADR-028 迁入体感栏目；ADR-029 F2 自 panels.tsx 逐字搬出。
// matter-js 只进本文件，不污染其他面板模块）
// 手柄倾斜 → 弹珠。物理在前端跑：matter.js（社区调校十年的 2D 引擎，A-maze Ball
// 同款）+ 240Hz 固定子步（matter 0.20 官方防穿墙姿势）。构建时打包进产物，终端用户
// 零 npm 感知。倾斜由后端 0xEF 运动流解算，40ms 轮询 + 前端低通。质感三件套：
// 板子随 tilt 微倾（Neverball 式「板是活的」）、球体自转纹理、撞墙音效+手柄震动。
// 面板同时是「手柄有没有真体感」的答案器：原始加速度/陀螺/数据源可见。
import { useEffect, useRef, useState } from 'react'
import { Bodies, Body, Composite, Engine, Events } from 'matter-js'
import { api } from '../../../api'
import { usePolling } from '../../../hooks/usePolling'
import { motionStore } from '../../../motionStore'
import { BTN, BTN_ACC, Err, Row, useFlash } from '../ui'

const MAZE_W = 560, MAZE_H = 360, BALL_R = 7
// 迷宫布局（v2，2026-09-21）：旧布局被 BFS 实锤结构性死路（H1 横墙切断 C2 上下，
// 而 C1 只能从底部进 C2，C2/C3 上半区永远进不去——用户实测到不了终点是对的）。
// v2 = 开阔蛇形五柱（每柱 ~100px 宽，通道远大于球径），S 形路线：下→上→下→上→下。
// 已用 backend/app/_maze_check.py BFS（含球半径净空+洞避让）验证全通。
const MAZE_WALLS: Array<[number, number, number, number]> = [
  [0, 0, MAZE_W, 8], [0, MAZE_H - 8, MAZE_W, 8], [0, 0, 8, MAZE_H], [MAZE_W - 8, 0, 8, MAZE_H],
  [110, 8, 8, 230], [220, 122, 8, 230], [330, 8, 8, 230], [440, 122, 8, 230],
]
const MAZE_HOLES = [
  { x: 60, y: 160, r: 13 }, { x: 170, y: 85, r: 13 }, { x: 280, y: 200, r: 13 },
]
const MAZE_GOAL = { x: 495, y: 296, w: 52, h: 50 }
const START = { x: 55, y: 45 }

function MazeBoard({ invX, invY }: { invX: boolean; invY: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const state = useRef({
    x: START.x, y: START.y, vx: 0, vy: 0,
    tx: 0, ty: 0,                  // 低通后的倾斜（进物理的值，防手柄微抖直灌）
    spin: 0,                       // 滚动相位（自转视觉）
    falls: 0, wins: 0, flash: '', flashT: 0,
    falling: 0,                    // >0 = 掉洞动画中（时间戳）
    t0: performance.now(), best: 0, reset: null as null | ((full?: boolean) => void),
  })
  useEffect(() => {
    const cv = ref.current
    if (!cv) return
    const g = cv.getContext('2d')
    if (!g) return
    let raf = 0
    let last = performance.now()
    // 音效：WebAudio 现场合成（零素材）；首次交互解锁（浏览器自动播放策略）
    let audio: AudioContext | null = null
    const unlock = () => {
      if (!audio) { try { audio = new AudioContext() } catch { /* 无音频环境 */ } }
      audio?.resume().catch(() => { })
    }
    window.addEventListener('pointerdown', unlock)
    unlock()
    const blip = (freq: number, vol: number, dur = 0.06, type: OscillatorType = 'triangle') => {
      if (!audio || audio.state !== 'running') return
      const t = audio.currentTime
      const o = audio.createOscillator(), gn = audio.createGain()
      o.type = type; o.frequency.value = freq
      gn.gain.setValueAtTime(vol, t)
      gn.gain.exponentialRampToValueAtTime(0.0001, t + dur)
      o.connect(gn); gn.connect(audio.destination)
      o.start(t); o.stop(t + dur + 0.01)
    }
    // 撞墙 → 手柄震动（强度∝撞击速度，节流；体感小游戏的「质感」闭环）
    let lastRumble = 0
    const rumble = (impact: number) => {
      const n = performance.now()
      if (n - lastRumble < 130) return
      lastRumble = n
      const k = Math.min(1, impact / 700)
      api.rumble(Math.max(0.12, k * 0.8), Math.max(0.12, k * 0.8), 110).catch(() => { })
    }
    // tilt 数据源：WS 推送 → motionStore（30Hz，零 HTTP 轮询、零 React 渲染）。
    // 旧版 40ms HTTP 轮询是「很卡、半天动一下」的根因之一。
    const reset = (full = false) => {
      const s = state.current
      Body.setPosition(ball, { x: START.x, y: START.y })
      Body.setVelocity(ball, { x: 0, y: 0 })
      Body.setAngularVelocity(ball, 0)
      s.spin = 0; s.falling = 0; s.tx = 0; s.ty = 0; s.t0 = performance.now()
      if (full) { s.wins = 0; s.falls = 0; s.best = 0 }
    }
    state.current.reset = reset
    // 物理核心：matter.js（社区调校十年的 2D 引擎，A-maze Ball 等口碑弹珠同款）。
    // 构建时打包进产物，终端用户零 npm 感知（ADR-028 D3：成熟轮子优先，依赖无感）。
    // 固定步长 240Hz 子步（matter 0.20 官方推荐姿势：防穿墙 + 帧率无关）。
    const engine = Engine.create({ enableSleeping: false })
    const ball = Bodies.circle(START.x, START.y, BALL_R, {
      restitution: 0.42,       // 撞墙弹性
      friction: 0.02,
      frictionAir: 0.008,      // 滚动阻尼（小值：停得自然不「黏」）
      frictionStatic: 0,
      density: 0.001,
    })
    Composite.add(engine.world, [
      ball,
      ...MAZE_WALLS.map(([wx, wy, ww, wh]) =>
        Bodies.rectangle(wx + ww / 2, wy + wh / 2, ww, wh, { isStatic: true })),
    ])
    const SUBSTEP_MS = 1000 / 240
    const MAXV = 3.1           // px/子步（≈745 px/s），穿墙保险
    const G_TILT = 1.6         // tilt(±1) → 引擎重力倍率
    // 撞墙反馈：collisionStart 相对法向速度（px/子步 → px/s）
    Events.on(engine, 'collisionStart', (ev) => {
      for (const pr of ev.pairs) {
        const n = pr.collision.normal
        const v = ball.velocity
        const impact = Math.abs(v.x * n.x + v.y * n.y) * 240
        if (impact > 90) {
          blip(140 + Math.min(300, impact * 0.5), Math.min(0.09, impact / 9000))
          rumble(impact)
        }
      }
    })
    const loop = () => {
      const now = performance.now()
      const dt = Math.min(0.05, (now - last) / 1000)
      last = now
      const s = state.current
      // 目标倾斜（面板反转在物理层生效）→ 一阶低通（时间常数 ~70ms）
      let gx = motionStore.tilt[0], gy = motionStore.tilt[1]
      if (invX) gx = -gx
      if (invY) gy = -gy
      const klp = Math.min(1, dt * 14)
      s.tx += (gx - s.tx) * klp
      s.ty += (gy - s.ty) * klp
      if (s.falling) {
        if (now - s.falling > 650) reset()
      } else {
        // tilt → 引擎重力向量（低通后直灌）；matter 240Hz 子步负责碰撞与积分
        engine.gravity.x = s.tx * G_TILT
        engine.gravity.y = s.ty * G_TILT
        for (let i = 0; i < 4; i++) Engine.update(engine, SUBSTEP_MS)
        { // 速度钳制（穿墙保险）
          const v = ball.velocity
          const sp = Math.hypot(v.x, v.y)
          if (sp > MAXV) Body.setVelocity(ball, { x: v.x * MAXV / sp, y: v.y * MAXV / sp })
        }
        // 引擎态 → 渲染态同步（px/子步 → px/s）
        s.x = ball.position.x; s.y = ball.position.y
        const bv = ball.velocity
        s.vx = bv.x * 240; s.vy = bv.y * 240
        const spd = Math.hypot(s.vx, s.vy)
        s.spin += spd * dt / BALL_R
        // 洞口：慢速靠近才被「吸」进去（引力感），快速掠过不陷——真实弹珠手感
        for (const ho of MAZE_HOLES) {
          const hx = ho.x - s.x, hy = ho.y - s.y
          const hd = Math.hypot(hx, hy)
          if (hd < ho.r + BALL_R) {
            if (spd < 340) {
              const pull = 1500 * (1 - hd / (ho.r + BALL_R)) * dt
              Body.setVelocity(ball, {
                x: ball.velocity.x + ((hx / (hd || 1)) * pull) / 240,
                y: ball.velocity.y + ((hy / (hd || 1)) * pull) / 240,
              })
            }
            if (hd < ho.r - 3) {
              s.falling = now; s.falls++
              s.flash = '掉洞了！'; s.flashT = now
              blip(90, 0.1, 0.28, 'sine')
              break
            }
          }
        }
        // 终点
        if (s.x > MAZE_GOAL.x && s.x < MAZE_GOAL.x + MAZE_GOAL.w &&
            s.y > MAZE_GOAL.y && s.y < MAZE_GOAL.y + MAZE_GOAL.h) {
          s.wins++
          const sec = (now - s.t0) / 1000
          if (!s.best || sec < s.best) s.best = sec
          s.flash = `到达终点！${sec.toFixed(1)}s`; s.flashT = now
          blip(520, 0.08, 0.1); setTimeout(() => blip(780, 0.08, 0.16), 110)
          reset()
        }
      }
      // 绘制：整块板随 tilt 微倾微缩（「板是活的」），物理坐标不动
      g.fillStyle = '#0b0b12'
      g.fillRect(0, 0, MAZE_W, MAZE_H)
      g.save()
      g.translate(MAZE_W / 2, MAZE_H / 2)
      g.rotate(s.tx * 0.07)
      g.scale(1 - Math.abs(s.ty) * 0.025, 1 - Math.abs(s.tx) * 0.025)
      g.translate(-MAZE_W / 2, -MAZE_H / 2)
      g.fillStyle = '#221d30'
      g.fillRect(4, 4, MAZE_W - 8, MAZE_H - 8)
      // 墙：主体 + 顶缘亮线（立体感）
      for (const [wx, wy, ww, wh] of MAZE_WALLS) {
        g.fillStyle = '#453f5e'
        g.fillRect(wx, wy, ww, wh)
        g.fillStyle = 'rgba(255,255,255,0.13)'
        g.fillRect(wx, wy, ww, Math.min(2, wh))
      }
      // 洞：径向渐变（深洞感）
      for (const h of MAZE_HOLES) {
        const rg = g.createRadialGradient(h.x, h.y, 1, h.x, h.y, h.r)
        rg.addColorStop(0, '#000'); rg.addColorStop(0.75, '#05050a'); rg.addColorStop(1, '#1a1626')
        g.fillStyle = rg
        g.beginPath(); g.arc(h.x, h.y, h.r, 0, 7); g.fill()
      }
      g.fillStyle = 'rgba(52,211,153,0.4)'
      g.fillRect(MAZE_GOAL.x, MAZE_GOAL.y, MAZE_GOAL.w, MAZE_GOAL.h)
      g.fillStyle = '#34d399'
      g.font = '10px sans-serif'; g.fillText('终点', MAZE_GOAL.x + 16, MAZE_GOAL.y + 28)
      // 弹珠：阴影（随倾斜偏移）+ 球体渐变 + 滚动纹理（三条纬线随 spin 转）
      const scale = s.falling ? Math.max(0, 1 - (now - s.falling) / 550) : 1
      if (scale > 0) {
        g.fillStyle = 'rgba(0,0,0,0.4)'
        g.beginPath()
        g.ellipse(s.x + s.tx * 4, s.y + s.ty * 4 + BALL_R * 0.55,
          BALL_R * 0.9 * scale, BALL_R * 0.42 * scale, 0, 0, 7)
        g.fill()
        const grd = g.createRadialGradient(
          s.x - BALL_R * 0.4, s.y - BALL_R * 0.45, BALL_R * 0.15, s.x, s.y, BALL_R)
        grd.addColorStop(0, '#cff8ff'); grd.addColorStop(0.55, '#38bdf8'); grd.addColorStop(1, '#0d5c84')
        g.fillStyle = grd
        g.beginPath(); g.arc(s.x, s.y, BALL_R * scale, 0, 7); g.fill()
        if (!s.falling && scale > 0.9) {          // 滚动纹理：表面纬线沿速度轴转动
          g.save()
          g.beginPath(); g.arc(s.x, s.y, BALL_R - 0.5, 0, 7); g.clip()
          g.translate(s.x, s.y)
          g.rotate(Math.atan2(s.vy, s.vx) + Math.PI / 2)
          g.strokeStyle = 'rgba(8,40,60,0.6)'; g.lineWidth = 1.5
          for (let k = 0; k < 3; k++) {
            const ph = s.spin + (k * Math.PI * 2) / 3
            const yy = Math.sin(ph) * BALL_R
            const half = Math.sqrt(Math.max(0, BALL_R * BALL_R - yy * yy)) * 0.96
            g.globalAlpha = 0.25 + 0.35 * Math.max(0, Math.cos(ph))
            g.beginPath(); g.moveTo(-half, yy); g.lineTo(half, yy); g.stroke()
          }
          g.restore()
          g.globalAlpha = 1
        }
      }
      if (s.flash && now - s.flashT < 1500) {
        g.fillStyle = '#fbbf24'; g.font = 'bold 18px sans-serif'
        g.fillText(s.flash, MAZE_W / 2 - 60, 30)
      }
      g.restore()
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => { cancelAnimationFrame(raf); window.removeEventListener('pointerdown', unlock) }
  }, [invX, invY])
  return (
    <div className="space-y-1">
      <canvas ref={ref} width={MAZE_W} height={MAZE_H} className="w-full rounded border border-border-soft" />
      <MazeHud state={state} />
    </div>
  )
}

function MazeHud({ state }: { state: React.MutableRefObject<any> }) {
  const [, force] = useState(0)
  usePolling(() => force(n => n + 1), 200)
  const s = state.current
  const sec = (performance.now() - s.t0) / 1000
  return (
    <div className="flex items-center gap-3 text-[10px] text-text-low">
      <span>本局 {sec.toFixed(1)}s{s.best ? ` · 最佳 ${s.best.toFixed(1)}s` : ''}</span>
      <span>到达 {s.wins}</span>
      <span>掉洞 {s.falls}</span>
      <button className={BTN + ' ml-auto'} onClick={() => s.reset?.(true)}>重开一局</button>
    </div>
  )
}

export function MazePanel() {
  const [tel, setTel] = useState<any>(null)
  const [msg, flash] = useFlash()
  const [inv, setInv] = useState(() => {
    try { return JSON.parse(localStorage.getItem('maze_inv') ?? '{"x":false,"y":false}') }
    catch { return { x: false, y: false } }
  })
  useEffect(() => { localStorage.setItem('maze_inv', JSON.stringify(inv)) }, [inv])
  // 遥测自检轮询（慢速 300ms，只喂诊断显示；实时 tilt 走 WS→motionStore，弹珠物理直读）
  usePolling(() => { api.expMaze().then(setTel).catch(() => { }) }, 300)
  // 反转在物理层生效（MazeBoard 读 tilt 时取反），存 localStorage 记住偏好
  const toggleInv = (k: 'x' | 'y') => setInv((c: any) => ({ ...c, [k]: !c[k] }))
  const imuOk = tel?.has_imu
  return (
    <div className="space-y-2.5">
      {/* 自检：回答「手柄到底有没有真体感」 */}
      <div className={`rounded-md border p-2 text-[11px] ${imuOk ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300' : 'border-red-500/40 bg-red-500/10 text-red-300'}`}>
        {tel === null ? '自检中…' : imuOk ? (
          <>
            ✓ 检测到体感数据流（{tel.source === 'gyro_fallback' ? '陀螺仪模式：固件未填加速度，用陀螺积分' : '加速度计+陀螺仪'}）
            <span className="ml-2 text-text-low">帧 {tel.frames} ｜ 加速度模长 {tel.accel_mag} ｜ 陀螺 ({tel.raw_gyro.join(', ')})</span>
          </>
        ) : (
          <>✗ 没有任何体感数据（加速度模长 {tel.accel_mag}，陀螺全 0）——当前模式下固件没输出运动数据，试试重启手柄或连 Switch 模式验证硬件</>
        )}
      </div>
      {/* 实时倾斜条：不用玩迷宫，放平→倾斜立刻能验证方向与增益是否对称 */}
      <div className="rounded-md border border-border-soft p-2">
        <div className="mb-1 flex items-center gap-2 text-[10px] text-text-low">
          实时倾斜
          <span className={tel?.autocal ? 'text-emerald-300' : 'text-amber-300'}>
            {tel?.autocal
              ? '锚点已锁定（软件不会再动它）'
              : tel?.anchor === 'flat' ? '平放静止中，正在锚定平地…' : '把手柄平放静止 1 秒以锚定平地'}
          </span>
          <span className="ml-2">
            {tel?.anchor === 'held' ? '（非平放：锚点保持不动）' : tel?.anchor === 'moving' ? '（运动中）' : ''}
          </span>
        </div>
        {(['x', 'y'] as const).map(k => {
          const v = Math.max(-1, Math.min(1, tel?.tilt?.[k === 'x' ? 0 : 1] ?? 0))
          return (
            <div key={k} className="mb-1 flex items-center gap-2 text-[10px] text-text-low">
              <span className="w-10">{k === 'x' ? '左右' : '前后'}</span>
              <div className="relative h-2 flex-1 rounded bg-white/10">
                <div className="absolute left-1/2 top-0 h-full w-px bg-white/30" />
                <div className={`absolute top-0 h-full rounded ${v >= 0 ? 'bg-cyan-400' : 'bg-amber-400'}`}
                  style={v >= 0
                    ? { left: '50%', width: `${v * 50}%` }
                    : { left: `${50 + v * 50}%`, width: `${-v * 50}%` }} />
              </div>
              <span className="w-14 text-right">{k === 'x' ? (v > 0.05 ? '偏右' : v < -0.05 ? '偏左' : '居中') : (v > 0.05 ? '偏后(向下滚)' : v < -0.05 ? '偏前(向上滚)' : '居中')}</span>
            </div>
          )
        })}
      </div>
      <Row label="校准">
        <button className={BTN_ACC} disabled={!imuOk || tel?.source === 'gyro_fallback'}
          onClick={() => api.expMazeCal().then(() => flash('✓ 锚点已重设为当前姿态')).catch(e => flash('', e))}>
          重设锚点为当前姿态
        </button>
        <span className="text-[10px] text-text-low">锚点只在第一次平放静止时自动采一次，之后软件不会再动它；只有你在这里手动点才会重设</span>
      </Row>
      <Row label="方向">
        <button className={inv.x ? BTN_ACC : BTN} onClick={() => toggleInv('x')}>左右 {inv.x ? '（已反转）' : '正常'}</button>
        <button className={inv.y ? BTN_ACC : BTN} onClick={() => toggleInv('y')}>前后 {inv.y ? '（已反转）' : '正常'}</button>
        <span className="text-[10px] text-text-low">滚反了点一下就正（记住偏好）</span>
      </Row>
      <MazeBoard invX={inv.x} invY={inv.y} />
      <Err e={msg} />
    </div>
  )
}
