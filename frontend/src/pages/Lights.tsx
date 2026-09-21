// 灯光工坊（ADR-018）：捏人式体验——所有改动自动写入（防抖 650ms + 串行队列），
// 大号手柄实时预览灯效（rAF 逐灯珠上色，与真机同款帧算法），右边风格库一键换装。
// 写入协议不变：效果 PC 侧展开 → 0xA8/0xA9 写入 → 读回自校验。
import { useEffect, useMemo, useRef, useState } from 'react'
import { Check, Dices, Loader2, Moon, RotateCcw, TriangleAlert } from 'lucide-react'
import { api, type LedBean } from '../api'

type Mode = 'off' | 'on' | 'breath' | 'gradient' | 'flow'

const MODES: Array<{ id: Mode; label: string; minColors: number }> = [
  { id: 'off', label: '熄灯', minColors: 0 },
  { id: 'on', label: '常亮', minColors: 1 },
  { id: 'breath', label: '呼吸', minColors: 1 },
  { id: 'gradient', label: '渐变', minColors: 2 },
  { id: 'flow', label: '流光', minColors: 1 },
]

const PRESETS: Array<{ name: string; colors: number[][]; mode: Mode; period?: number }> = [
  { name: '冰蓝常亮', colors: [[0, 170, 255]], mode: 'on' },
  { name: '红色呼吸', colors: [[255, 30, 30]], mode: 'breath' },
  { name: '赛博渐变', colors: [[255, 0, 200], [0, 220, 255]], mode: 'gradient' },
  { name: '极光', colors: [[0, 255, 140], [0, 120, 255], [160, 0, 255]], mode: 'gradient' },
  { name: '日落', colors: [[255, 120, 0], [255, 40, 80], [180, 0, 220]], mode: 'gradient' },
  { name: '彩虹流光', colors: [[255, 0, 0], [255, 200, 0], [0, 255, 60], [0, 200, 255], [120, 0, 255]], mode: 'flow' },
  { name: '警灯', colors: [[255, 20, 20], [20, 80, 255]], mode: 'flow', period: 4 },
  { name: '薄荷呼吸', colors: [[60, 255, 180]], mode: 'breath' },
]

// ---- 颜色工具 ----
const hex = (c: number[]) => '#' + c.map(v => Math.round(v).toString(16).padStart(2, '0')).join('')
const lerp = (a: number, b: number, u: number) => a + (b - a) * u

/** 循环调色板采样：u∈[0,1) 在首尾相接的色环上取色（渐变/流光共用） */
function samplePalette(stops: number[][], u: number): number[] {
  const n = stops.length
  if (n === 0) return [255, 255, 255]
  if (n === 1) return stops[0]
  const x = ((u % 1) + 1) % 1 * n
  const i = Math.floor(x) % n
  const j = (i + 1) % n
  const f = x - Math.floor(x)
  // 平滑缓动让相邻色过渡更"高级"（捏人预览质感的关键之一）
  const s = f * f * (3 - 2 * f)
  return [lerp(stops[i][0], stops[j][0], s), lerp(stops[i][1], stops[j][1], s), lerp(stops[i][2], stops[j][2], s)]
}

/** 灯珠颜色帧算法：与真机效果同思路（呼吸正弦 / 渐变环采样 / 流光彗尾），t 为归一化周期相位 */
function ledColor(mode: Mode, stops: number[][], idx: number, n: number, t: number): number[] {
  if (mode === 'off' || stops.length === 0) return [0, 0, 0]
  if (mode === 'on') return stops[0]
  if (mode === 'breath') {
    const k = 0.5 - 0.5 * Math.cos(t * Math.PI * 2)      // 0→1→0 余弦呼吸
    const s = 0.12 + 0.88 * k                            // 底亮 12%，不真灭（和"熄灯"区分）
    return stops[0].map(v => v * s)
  }
  if (mode === 'gradient') {
    const drift = t * 0.15                               // 整条色带缓慢流动
    return samplePalette(stops, idx / Math.max(1, n - 1) + drift)
  }
  // flow：彗尾扫过，头亮尾暗
  const head = t * n
  const d = ((idx - head) % n + n) % n                   // 落后头的距离
  const tail = Math.max(3, n * 0.55)
  const fade = d < tail ? 1 - d / tail : 0
  const c = samplePalette(stops, idx / n)
  return c.map(v => v * (0.08 + 0.92 * fade * fade))
}

// ---- 实时预览：大号手柄 + rgb_num 颗灯珠逐帧上色 ----
function PadPreview({ mode, colors, brightness, period, rgbNum }: {
  mode: Mode; colors: number[][]; brightness: number; period: number; rgbNum: number
}) {
  const [t, setT] = useState(0)
  useEffect(() => {
    // 周期映射：真机"帧距"1-60 → 预览 0.8s~6s 一循环；熄灯/常亮不用跑动画
    const dur = Math.max(0.8, period * 0.1)
    let raf = 0
    let last = 0
    const tick = (now: number) => {
      if (now - last > 33) {                             // ~30fps 足够，省电
        last = now
        setT((now / 1000 / dur) % 1)
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [period])

  const lit = mode !== 'off'
  const glow = lit ? 0.25 + 0.75 * (brightness / 255) : 0
  const dots = useMemo(() => Array.from({ length: rgbNum }, (_, i) => {
    // 灯珠排布：沿手柄下缘从左握把→右握把的弧线（真机物理位置未知，示意等价）
    const u = i / Math.max(1, rgbNum - 1)
    const x = 90 + u * 180
    const y = 118 + Math.sin(u * Math.PI) * 16
    return { x, y }
  }), [rgbNum])

  return (
    <div className="relative flex items-center justify-center overflow-hidden rounded-xl border border-border-soft bg-[#0a0a12] p-2">
      {/* 环境光晕：跟着主色走，这是"花里胡哨"的氛围底 */}
      <div className="pointer-events-none absolute inset-0 transition-colors duration-500"
        style={{ background: `radial-gradient(ellipse 70% 60% at 50% 65%, rgba(${colors[0]?.join(',') ?? '0,170,255'},${0.16 * glow}), transparent 70%)` }} />
      <svg viewBox="0 0 360 170" className="relative w-full max-w-md">
        {/* 手柄轮廓 */}
        <g fill="#101018" stroke="#23233a" strokeWidth="2">
          <rect x="70" y="52" width="220" height="52" rx="26" />
          <ellipse cx="86" cy="98" rx="42" ry="46" />
          <ellipse cx="274" cy="98" rx="42" ry="46" />
        </g>
        {/* 摇杆/按键示意（深色浮雕，不抢灯珠戏） */}
        <circle cx="86" cy="98" r="16" fill="#161624" stroke="#23233a" />
        <circle cx="274" cy="98" r="16" fill="#161624" stroke="#23233a" />
        {[[196, 66], [212, 60], [228, 66], [212, 76]].map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r="5" fill="#161624" stroke="#23233a" />
        ))}
        {/* 灯珠：逐帧上色 + 辉光随亮度 */}
        {dots.map((d, i) => {
          const c = ledColor(mode, colors, i, rgbNum, t)
          const a = Math.max(...c) / 255
          return (
            <circle key={i} cx={d.x} cy={d.y} r="4.5"
              fill={hex(c)}
              style={{ filter: `drop-shadow(0 0 ${(2 + 5 * a * glow).toFixed(1)}px rgba(${c.map(Math.round).join(',')},${(a * glow).toFixed(2)}))` }} />
          )
        })}
      </svg>
    </div>
  )
}

/** 风格卡迷你预览：4fps 自走帧（低频 interval，8 张卡也不费电），预览同款帧算法 */
function MiniStrip({ mode, colors }: { mode: Mode; colors: number[][] }) {
  const [t, setT] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setT(v => (v + 0.04) % 1), 250)
    return () => clearInterval(id)
  }, [])
  return (
    <div className="mb-1.5 flex h-5 items-end gap-0.5 overflow-hidden rounded bg-black/40">
      {Array.from({ length: 8 }, (_, i) => (
        <span key={i} className="h-full flex-1 rounded-sm transition-colors duration-200"
          style={{ background: hex(ledColor(mode, colors, i, 8, t)) }} />
      ))}
    </div>
  )
}

type Sync = 'idle' | 'queued' | 'writing' | 'ok' | 'err'

export default function Lights() {
  const [bean, setBean] = useState<LedBean | null>(null)
  const [mode, setMode] = useState<Mode>('breath')
  const [colors, setColors] = useState<number[][]>([[0, 170, 255]])
  const [brightness, setBrightness] = useState(128)
  const [period, setPeriod] = useState(10)
  const [sync, setSync] = useState<Sync>('idle')
  const [syncMsg, setSyncMsg] = useState('')

  // ---- 自动写入引擎：650ms 防抖 + 串行队列（写一次 ~1-2s，绝不能并发打手柄） ----
  const touched = useRef(false)          // 首次进页不回写：状态以设备为准
  const timer = useRef(0)
  const writing = useRef(false)

  const refresh = () => api.ledConfig().then(r => setBean(r.bean)).catch(() => {})
  useEffect(() => { refresh() }, [])

  const spec = MODES.find(m => m.id === mode)!
  const ready = spec.minColors === 0 || colors.length >= spec.minColors

  const runSync = async () => {
    if (writing.current) { scheduleSync(); return }      // 写盘中又改了 → 写完再补一轮
    if (!ready) { setSync('idle'); return }
    writing.current = true
    setSync('writing')
    try {
      await api.ledApply(mode, mode === 'off' ? [] : colors, mode === 'off' ? undefined : brightness, period)
      setSync('ok')
      refresh()
    } catch (e) {
      setSync('err')
      setSyncMsg((e as Error).message)
    }
    writing.current = false
  }
  const scheduleSync = () => {
    if (!touched.current) return
    window.clearTimeout(timer.current)
    setSync('queued')
    timer.current = window.setTimeout(runSync, 650)
  }
  useEffect(() => { scheduleSync() }, [mode, colors, brightness, period])  // eslint-disable-line react-hooks/exhaustive-deps

  // ---- 交互：任何改动都标记 touched（首次加载的 useEffect 不触发回写） ----
  const change = (fn: () => void) => { touched.current = true; fn() }
  const applyStyle = (m: Mode, cs: number[][], p?: number) => change(() => {
    setMode(m); setColors(cs); if (p) setPeriod(p)
  })
  const setColor = (i: number, v: string) => change(() => {
    const rgb = [parseInt(v.slice(1, 3), 16), parseInt(v.slice(3, 5), 16), parseInt(v.slice(5, 7), 16)]
    setColors(cs => cs.map((c, j) => (j === i ? rgb : c)))
  })
  const randomStyle = () => change(() => {
    // 随机配色：主色随机 + 谐和色相偏移（捏人"随机外观"的同款快乐）
    const h = Math.random() * 360
    const mk = (dh: number, s: number, l: number) => hslToRgb((h + dh + 360) % 360, s, l)
    const cs = [mk(0, 0.85, 0.55), mk(140, 0.8, 0.5), mk(220, 0.85, 0.6)]
    setMode('gradient'); setColors(cs)
  })
  const restore = async () => {
    setSync('writing')
    try { await api.ledRestore(); setSync('ok'); refresh() } catch (e) { setSync('err'); setSyncMsg((e as Error).message) }
  }

  const SYNC_UI: Record<Sync, { text: string; cls: string; icon?: React.ReactNode }> = {
    idle: { text: '待机', cls: 'border-border-soft bg-white/5 text-text-low' },
    queued: { text: '等待改动停止…', cls: 'border-warn/40 bg-warn/10 text-warn' },
    writing: { text: '写入灯表…', cls: 'border-accent/40 bg-accent/10 text-accent' },
    ok: { text: '已同步到灯表', cls: 'border-ok/40 bg-ok/10 text-ok' },
    err: { text: `同步失败：${syncMsg}`, cls: 'border-err/40 bg-err/10 text-err' },
  }
  const su = SYNC_UI[sync]

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      {/* 顶栏：标题 + 同步状态（自动写入的灵魂是让用户随时知道同步到哪一步了） */}
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[15px] font-semibold text-text-hi">灯光工坊</div>
          <div className="text-[11px] text-text-low">改什么亮什么——所有调整自动写入手柄，不用点保存</div>
        </div>
        <div className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[11px] ${su.cls}`} data-sync={sync}>
          {sync === 'writing' && <Loader2 size={12} className="animate-spin" />}
          {sync === 'ok' && <Check size={12} />}
          {sync === 'err' && <TriangleAlert size={12} />}
          {su.text}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_300px]">
        {/* 左：预览台 + 调参（捏人的"照镜子"区） */}
        <div className="space-y-4">
          <PadPreview mode={mode} colors={colors} brightness={brightness} period={period} rgbNum={bean?.rgb_num ?? 10} />

          <div className="card space-y-4 p-4">
            {/* 模式 */}
            <div>
              <div className="mb-2 text-[12px] text-text-mid">灯效模式</div>
              <div className="flex flex-wrap gap-1.5">
                {MODES.map(m => (
                  <button key={m.id} onClick={() => change(() => setMode(m.id))}
                    className={`rounded-lg border px-3 py-1.5 text-[12px] transition-all ${
                      mode === m.id ? 'border-accent/50 bg-accent/15 text-accent' : 'border-transparent text-text-mid hover:bg-white/4'}`}>
                    {m.label}
                  </button>
                ))}
              </div>
              {spec.minColors > 1 && colors.length < spec.minColors && (
                <div className="mt-1.5 text-[11px] text-warn">{spec.label}至少需要 {spec.minColors} 个颜色</div>
              )}
            </div>

            {/* 配色槽位 */}
            {mode !== 'off' && (
              <div>
                <div className="mb-2 flex items-center gap-2 text-[12px] text-text-mid">
                  配色槽位
                  <span className="text-text-low">（点色块改色，最多 5 格）</span>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {colors.map((c, i) => (
                    <label key={i} className="group relative h-11 w-11 cursor-pointer overflow-hidden rounded-xl border-2 border-white/15 transition-transform hover:scale-105"
                      style={{ background: hex(c), boxShadow: `0 0 14px ${hex(c)}66` }}>
                      <input type="color" value={hex(c)} onChange={e => setColor(i, e.target.value)}
                        className="absolute inset-0 cursor-pointer opacity-0" />
                    </label>
                  ))}
                  {colors.length < 5 && (
                    <button className="flex h-11 w-11 items-center justify-center rounded-xl border border-dashed border-border-soft text-text-low transition-colors hover:border-accent/50 hover:text-accent"
                      onClick={() => change(() => setColors(cs => [...cs, [255, 255, 255]]))}>+</button>
                  )}
                  {colors.length > 1 && (
                    <button className="flex h-11 w-11 items-center justify-center rounded-xl border border-dashed border-border-soft text-text-low transition-colors hover:border-err/50 hover:text-err"
                      onClick={() => change(() => setColors(cs => cs.slice(0, -1)))}>-</button>
                  )}
                  <button className="btn !px-3 !py-1.5 text-[12px]" onClick={randomStyle} title="随机一套谐和配色">
                    <Dices size={13} /> 随机
                  </button>
                </div>
              </div>
            )}

            {/* 亮度 / 速度 */}
            {mode !== 'off' && (
              <div className="grid grid-cols-2 gap-4">
                <label className="text-[12px] text-text-mid">
                  亮度 <span className="font-mono text-accent">{brightness}</span>
                  <input type="range" min={1} max={255} value={brightness}
                    onChange={e => change(() => setBrightness(+e.target.value))} className="mt-1 w-full accent-[#22d3ee]" />
                </label>
                <label className="text-[12px] text-text-mid">
                  节奏 <span className="font-mono text-accent">{period}</span>
                  <input type="range" min={1} max={60} value={period}
                    onChange={e => change(() => setPeriod(+e.target.value))} className="mt-1 w-full accent-[#22d3ee]" />
                </label>
              </div>
            )}

            {bean && (
              <div className="font-mono text-[11px] text-text-low">
                设备灯表：V{bean.version} · {bean.rgb_num} 灯珠 · 亮度 {bean.brightness} · 帧距 {bean.loop_time}
              </div>
            )}
          </div>
        </div>

        {/* 右：风格库（捏人的"预设外观"区） */}
        <div className="space-y-4">
          <div className="card p-4">
            <div className="mb-3 text-[13px] font-medium">风格库</div>
            <div className="grid grid-cols-2 gap-2">
              {PRESETS.map(p => (
                <button key={p.name} onClick={() => applyStyle(p.mode, p.colors, p.period)}
                  className={`group rounded-lg border p-2 text-left transition-all hover:border-accent/40 ${
                    mode === p.mode && hex(colors[0] ?? []) === hex(p.colors[0]) ? 'border-accent/50 bg-accent/10' : 'border-border-soft'}`}>
                  {/* 迷你动画条：预览同款算法的小样 */}
                  <MiniStrip mode={p.mode} colors={p.colors} />
                  <div className="text-[11px] text-text-mid group-hover:text-text-hi">{p.name}</div>
                </button>
              ))}
            </div>
          </div>

          <div className="card space-y-2 p-4">
            <div className="text-[13px] font-medium">设备操作</div>
            <button onClick={() => applyStyle('off', [])}
              className="btn w-full justify-center border-warn/50 text-warn"
              title="灯表写全黑，整柄熄灯；想开回来选任意模式即可">
              <Moon size={13} /> 一键熄灯
            </button>
            <button onClick={restore} className="btn w-full justify-center" title="写回备份的灯表（官方彩虹等）">
              <RotateCcw size={13} /> 恢复官方灯表
            </button>
            <p className="pt-1 text-[11px] leading-relaxed text-text-low">
              写入即驻留：设备端循环播放，重启手柄仍生效。首次使用建议先「恢复官方灯表」生成一次备份。
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

// HSL→RGB（随机配色用）
function hslToRgb(h: number, s: number, l: number): number[] {
  const f = (n: number) => {
    const k = (n + h / 30) % 12
    const a = s * Math.min(l, 1 - l)
    return Math.round(255 * (l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1))))
  }
  return [f(0), f(8), f(4)]
}
