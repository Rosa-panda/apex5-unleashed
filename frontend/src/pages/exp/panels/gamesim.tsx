// #16 模拟游戏场（ADR-029 F2 自 panels.tsx 逐字搬出）
// 自己给自己当一个「游戏」：四个测试场覆盖全功能链路。
// 扳机场/灯场的事件走真实 UDP 链路（DSX 协议→ingress→cmd51；RGB→灯效桥→灯表），
// 与真游戏 Mod 同一条路；靶场/键盘场在本地跑，闭环测体感瞄准、摇杆映射、连发、宏。
import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../../api'
import { usePolling } from '../../../hooks/usePolling'
import { BTN, Err, NoDev, Row, useFlash } from '../ui'

// 靶场：鼠标轨迹 + 随机靶子打分——体感瞄准/摇杆转鼠标的闭环验证
function AimRange() {
  const ref = useRef<HTMLCanvasElement>(null)
  const [score, setScore] = useState(0)
  const [shots, setShots] = useState(0)
  const sim = useRef({
    trail: [] as Array<{ x: number; y: number; t: number }>,
    targets: [] as Array<{ x: number; y: number; r: number; born: number }>,
    mx: 0, my: 0,
  })
  useEffect(() => {
    const cv = ref.current
    if (!cv) return
    const g = cv.getContext('2d')
    if (!g) return
    const W = cv.width, H = cv.height
    const spawn = () => sim.current.targets.push({
      x: 30 + Math.random() * (W - 60), y: 30 + Math.random() * (H - 60),
      r: 14 + Math.random() * 12, born: performance.now(),
    })
    spawn()
    let raf = 0
    const loop = () => {
      const now = performance.now()
      sim.current.targets = sim.current.targets.filter(t => now - t.born < 4000)
      if (sim.current.targets.length === 0) spawn()
      g.fillStyle = 'rgba(0,0,0,0.28)'
      g.fillRect(0, 0, W, H)
      // 轨迹（2s 淡出）——体感移动是否流畅、有没有跳变，一眼可见
      sim.current.trail = sim.current.trail.filter(p => now - p.t < 2000)
      g.strokeStyle = 'rgba(34,211,238,0.5)'
      g.beginPath()
      sim.current.trail.forEach((p, i) => (i ? g.lineTo(p.x, p.y) : g.moveTo(p.x, p.y)))
      g.stroke()
      sim.current.targets.forEach(t => {
        const age = (now - t.born) / 4000
        g.strokeStyle = `rgba(251,191,36,${1 - age * 0.6})`
        g.beginPath(); g.arc(t.x, t.y, t.r, 0, 7); g.stroke()
        g.fillStyle = `rgba(251,191,36,${0.25 - age * 0.2})`
        g.fill()
      })
      g.fillStyle = '#67e8f9'
      g.beginPath(); g.arc(sim.current.mx, sim.current.my, 3, 0, 7); g.fill()
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [])
  const track = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    const p = { x: e.clientX - r.left, y: e.clientY - r.top, t: performance.now() }
    sim.current.mx = p.x; sim.current.my = p.y
    sim.current.trail.push(p)
    if (sim.current.trail.length > 400) sim.current.trail.shift()
  }
  const shoot = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    const x = e.clientX - r.left, y = e.clientY - r.top
    setShots(s => s + 1)
    if (sim.current.targets.some(t => (x - t.x) ** 2 + (y - t.y) ** 2 <= t.r ** 2)) {
      setScore(s => s + 1)
      sim.current.targets = sim.current.targets.filter(t => (x - t.x) ** 2 + (y - t.y) ** 2 > t.r ** 2)
    }
  }
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-3 text-[10px] text-text-low">
        <span>用体感/摇杆映射出的鼠标来瞄准打靶（先在测试区开启体感瞄准或摇杆→鼠标）</span>
        <span className="text-accent">命中 {score}</span>
        <span>/ 开枪 {shots}</span>
      </div>
      <canvas ref={ref} width={560} height={200}
        className="w-full cursor-crosshair rounded border border-border-soft"
        onMouseMove={track} onClick={shoot} />
    </div>
  )
}

// 键盘场：按键计数 + 频率——测固件连发（键表→键盘）、宏、摇杆转键盘
function KeyRange() {
  const [keys, setKeys] = useState<Record<string, { count: number; ts: number[]; down: boolean }>>({})
  useEffect(() => {
    const hit = (ev: KeyboardEvent, down: boolean) => {
      if (down && ev.repeat) return                 // 系统自动重复不算，只数真实按下
      const k = ev.key === ' ' ? 'Space' : ev.key
      setKeys(cur => {
        const e = cur[k] ?? { count: 0, ts: [], down: false }
        return { ...cur, [k]: down
          ? { count: e.count + 1, ts: [...e.ts.slice(-40), performance.now()], down: true }
          : { ...e, down: false } }
      })
    }
    const dn = (e: KeyboardEvent) => hit(e, true)
    const up = (e: KeyboardEvent) => hit(e, false)
    window.addEventListener('keydown', dn)
    window.addEventListener('keyup', up)
    return () => { window.removeEventListener('keydown', dn); window.removeEventListener('keyup', up) }
  }, [])
  const rows = Object.entries(keys).filter(([, e]) => e.count > 0).slice(-8)
  return (
    <div className="space-y-1">
      <div className="text-[10px] text-text-low">
        手柄键映射成键盘（测试区 → 连发 Turbo / 摇杆→键盘 / 宏）后在这里按——次数和实时频率一眼可见，连发是否生效立刻知道
      </div>
      <div className="flex flex-wrap gap-1.5">
        {rows.length === 0 && <span className="text-[11px] text-text-low">（在这个窗口里按键开始计数）</span>}
        {rows.map(([k, e]) => {
          const recent = e.ts.filter(t => performance.now() - t < 2000).length
          return (
            <span key={k} className={`rounded border px-2 py-1 text-[11px] ${e.down ? 'border-accent/60 bg-accent/10 text-accent' : 'border-border-soft text-text-mid'}`}>
              {k} × {e.count}{recent >= 2 ? ` · ${(recent / 2).toFixed(1)}/s` : ''}
            </span>
          )
        })}
      </div>
    </div>
  )
}

export function GameSimPanel() {
  const [st, setSt] = useState<any>(null)
  const [msg, flash] = useFlash()
  const load = useCallback(() => { api.expSim().then(setSt).catch(e => flash('', e)) }, [])
  usePolling(load, 1500, [load])
  if (!st) return <div className="space-y-2"><NoDev /><Err e={msg} /></div>
  const run = (s: string) =>
    api.expSimRun(s).then((r: any) => { setSt(r); flash(`▶ ${r.scenarios?.[s] ?? s}`) }).catch(e => flash('', e))
  const btn = (s: string, label: string, cls = BTN) => (
    <button className={cls} onClick={() => run(s)}>{label}</button>
  )
  return (
    <div className="space-y-2.5">
      <div className="flex flex-wrap items-center gap-2 text-[10px] text-text-low">
        <span>{st.running ? <b className="text-accent">运行中：{st.scenarios?.[st.running] ?? st.running}</b> : '空闲'}</span>
        <span>· DSX 包 {st.stats?.dsx_sent ?? 0}</span>
        <span>· RGB 包 {st.stats?.rgb_sent ?? 0}</span>
        <span>· 场次 {st.stats?.runs ?? 0}</span>
      </div>
      <Row label="扳机场">
        {btn('shooting', '射击 6s')}
        {btn('explosion', '爆炸')}
        {btn('race', '赛车 8s')}
        {btn('idle', '松开复位')}
      </Row>
      <Row label="灯场">
        {btn('lowhp', '低血量（红）')}
        {btn('heal', '回血（绿）')}
        {btn('idle', '熄灯')}
        <span className="text-[10px] text-text-low">需先启动「Mod 灯效桥」——RGB 走真实桥链路</span>
      </Row>
      {st.stats?.note && <Err e={st.stats.note} />}
      <div className="rounded-md border border-border-soft p-2">
        <div className="mb-1 text-[10px] text-text-low">靶场 · 体感瞄准 / 摇杆→鼠标 闭环验证</div>
        <AimRange />
      </div>
      <div className="rounded-md border border-border-soft p-2">
        <div className="mb-1 text-[10px] text-text-low">键盘场 · 连发 / 宏 / 摇杆→键盘 闭环验证</div>
        <KeyRange />
      </div>
      <div className="text-[10px] text-text-low">
        扳机/灯事件与真游戏 Mod 同一条 UDP 链路（DSX 协议→ingress→cmd51；RGB→桥→灯表），这里通了真游戏就通。
      </div>
      <Err e={msg} />
    </div>
  )
}
