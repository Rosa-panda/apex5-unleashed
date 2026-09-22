// 灯光工坊（ADR-018）：统一灯效库——风格库就是灯效选择器，点卡片换灯效；
// 任何手动改色/改参自动转入「自定义」（不动原预设），650ms 防抖自动写灯表。
// 预览算法与后端帧生成器同思路（gradient=整条过渡 / flow=空间相位流动 / …）。
import { useEffect, useMemo, useRef, useState } from 'react'
import { Check, Dices, Loader2, RotateCcw, TriangleAlert } from 'lucide-react'
import { api, type LedBean, type LedDetect } from '../api'

type Mode = 'off' | 'on' | 'breath' | 'gradient' | 'flow' | 'blink' | 'heartbeat' | 'wipe' | 'comet' | 'duosweep' | 'rain' | 'chase' | 'pulse' | 'fire' | 'auroraflow' | 'typewriter' | 'rainbow' | 'aurora'

interface Style { id: string; name: string; mode: Mode; colors: number[][]; period?: number }

/** 灯效库：mode 由卡片决定，颜色可自定义（编辑后转入「自定义」卡，原预设不动） */
const LIB: Style[] = [
  { id: 'ice', name: '冰蓝常亮', mode: 'on', colors: [[0, 170, 255]] },
  { id: 'red-breath', name: '红色呼吸', mode: 'breath', colors: [[255, 30, 30]] },
  { id: 'mint-breath', name: '薄荷呼吸', mode: 'breath', colors: [[60, 255, 180]] },
  { id: 'cyber', name: '赛博渐变', mode: 'gradient', colors: [[255, 0, 200], [0, 220, 255]] },
  { id: 'sunset', name: '日落渐变', mode: 'gradient', colors: [[255, 120, 0], [255, 40, 80], [180, 0, 220]] },
  { id: 'aurora', name: '极光', mode: 'aurora', colors: [[0, 255, 140], [0, 120, 255], [160, 0, 255]] },
  { id: 'rainbow', name: '彩虹循环', mode: 'rainbow', colors: [[255, 0, 0]] },
  { id: 'wipe', name: '扫描', mode: 'wipe', colors: [[0, 170, 255]] },
  { id: 'comet', name: '扫描·循环', mode: 'comet', colors: [[0, 170, 255]] },
  { id: 'duo', name: '双色对扫', mode: 'duosweep', colors: [[0, 170, 255], [255, 0, 140]] },
  { id: 'rain', name: '彗星雨', mode: 'rain', colors: [[0, 170, 255]] },
  { id: 'chase', name: '双色追及', mode: 'chase', colors: [[0, 170, 255], [255, 0, 140]] },
  { id: 'pulse', name: '中心脉冲', mode: 'pulse', colors: [[255, 40, 90]] },
  { id: 'fire', name: '火苗', mode: 'fire', colors: [[255, 120, 30]] },
  { id: 'auroraflow', name: '呼吸流光', mode: 'auroraflow', colors: [[0, 255, 140], [0, 120, 255], [160, 0, 255]] },
  { id: 'typewriter', name: '打字机', mode: 'typewriter', colors: [[0, 255, 140]] },
  { id: 'flow', name: '极电流光', mode: 'flow', colors: [[0, 255, 255], [80, 0, 255]], period: 8 },
]

/** 编辑态样式（排在库最前）：改色/改参自动转入，原预设永远不被污染 */
const CUSTOM: Style = { id: 'custom', name: '自定义', mode: 'breath', colors: [[0, 170, 255]] }
const OFF_STYLE: Style = { id: 'off', name: '熄灯', mode: 'off', colors: [] }

/** 各灯效的帧数（与 protocol.led_frames_* 生成器一致，预览按帧驱动） */
const STEPS: Record<Mode, number> = {
  off: 1, on: 1, breath: 15, gradient: 16, flow: 16,
  blink: 4, heartbeat: 12, wipe: 20, comet: 12, duosweep: 6, rain: 15, chase: 12,
  pulse: 11, fire: 16, auroraflow: 24, typewriter: 17, rainbow: 24, aurora: 24,
}

/** 依赖灯珠数的动态步数（与后端生成器一一对应）；静态灯效走 STEPS */
function stepsFor(mode: Mode, rgbNum: number): number {
  switch (mode) {
    case 'comet': return Math.max(2, rgbNum)
    case 'duosweep': return Math.max(2, Math.ceil(rgbNum / 2) + 2)   // +2 喘息拍
    case 'wipe': return Math.max(2, rgbNum * 2)
    case 'rain': return Math.max(2, rgbNum + 3)
    case 'chase': return Math.max(2, rgbNum)
    case 'pulse': return Math.max(2, 2 * Math.ceil(rgbNum / 2) - 1)
    case 'typewriter': return Math.max(2, rgbNum + 5)
    default: return STEPS[mode]
  }
}
/** 帧距→毫秒换算（真机近似标定：官方彩虹 lt=4、循环 ~10 帧、目测 3~4s/圈 ≈ 100ms/单位） */
const MS_PER_LT = 100

// 速度⇄帧距对数映射：设备帧距与感知速度是倒数关系，滑条线性分配会两头失真
// （帧距 30→40 几乎没差别，50→60 直接从动到不动）。对数映射后每格感知均匀。
const speedToLt = (v: number) =>
  Math.max(1, Math.min(60, Math.round(Math.exp(Math.log(60) * (1 - (v - 1) / 59)))))
const ltToSpeed = (lt: number) =>
  Math.max(1, Math.min(60, Math.round(1 + 59 * (1 - Math.log(Math.max(1, lt)) / Math.log(60)))))

// ---- 颜色工具（与后端帧生成器同思路：线性插值） ----
const hex = (c: number[]) => '#' + c.map(v => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, '0')).join('')
const mix = (a: number[], b: number[], f: number) => [0, 1, 2].map(k => a[k] + (b[k] - a[k]) * f)

/** 循环调色板采样：u∈[0,1) 在首尾相接的色环上线性取色 */
function samplePalette(stops: number[][], u: number): number[] {
  const n = stops.length
  if (n === 0) return [255, 255, 255]
  if (n === 1) return stops[0]
  const x = (((u % 1) + 1) % 1) * n
  const j = Math.floor(x) % n
  return mix(stops[j], stops[(j + 1) % n], x - Math.floor(x))
}

/** 灯珠颜色帧算法（镜像后端 protocol.led_frames_*）：t 为归一化循环相位 */
function ledColor(mode: Mode, stops: number[][], idx: number, n: number, t: number): number[] {
  if (mode === 'off' || stops.length === 0) return [0, 0, 0]
  switch (mode) {
    case 'on':
      return stops[0]
    case 'breath': {                       // 线性 ramp 0→1→0（真机 16 帧同款）
      const tri = t < 0.5 ? t * 2 : 2 - t * 2
      const s = 0.06 + 0.94 * tri
      return stops[0].map(v => v * s)
    }
    case 'gradient':                       // 整条同色，随时间在调色板间过渡
      return samplePalette(stops, t)
    case 'flow': {                         // 色相沿灯珠空间分布，随帧平移
      const m = stops.length
      const u = (idx / n + t) % 1 * m
      const j = Math.floor(u) % m
      return mix(stops[j], stops[(j + 1) % m], u - Math.floor(u))
    }
    case 'blink':                          // 4 帧亮灭方波
      return Math.floor(t * 4) % 2 === 0 ? stops[0] : [0, 0, 0]
    case 'heartbeat': {                    // 双峰包络（12 帧）
      const env = [0, 1, 0.55, 0, 0, 0.6, 0.3, 0, 0, 0, 0, 0]
      const k = env[Math.min(11, Math.floor(t * 12))]
      return stops[0].map(v => v * k)
    }
    case 'wipe': {                         // 逐珠点亮→逐珠熄灭
      const head = t < 0.5 ? t * 2 * n : (1 - (t - 0.5) * 2) * n
      return idx < head ? stops[0] : [0, 0, 0]
    }
    case 'comet': {                        // 扫描·循环（ADR-033）：逐珠点亮，铺满即从头再来
      const head = t * n
      return idx < head ? stops[0] : [0, 0, 0]
    }
    case 'duosweep': {                     // 双色对扫（修订 4）：相向铺满→相遇融合→喘息两拍
      const steps = Math.ceil(n / 2) + 2
      const k = Math.floor(t * steps)
      if (k >= Math.ceil(n / 2)) return [0, 0, 0]        // 表尾喘息拍
      const met = (n - 1 - k) - k <= 1
      const mix = stops[0].map((v, c) => Math.floor((v + stops[1 % stops.length][c]) / 2))
      if (idx <= k && idx >= n - 1 - k) return mix       // 相遇处两色融合
      if (met && (idx === k || idx === n - 1 - k)) return mix
      if (idx <= k) return stops[0]
      if (idx >= n - 1 - k) return stops[1 % stops.length]
      return [0, 0, 0]
    }
    case 'rain': {                         // 彗星雨：亮头拖尾连续掠过，一颗接一颗
      const tail = 3
      const p = t * (n + tail)
      const d = p - idx
      return d < 0 || d > tail ? [0, 0, 0]
        : stops[0].map(v => v * ((tail + 1 - d) / (tail + 1)))
    }
    case 'chase': {                        // 双色追及：B 三倍速追 A，分界游走
      const k = Math.floor(t * n)
      const pa = k % n, pb = (k * 3) % n
      const da = Math.min((idx - pa + n) % n, (pa - idx + n) % n)
      const db = Math.min((idx - pb + n) % n, (pb - idx + n) % n)
      return da <= db ? stops[0] : stops[1 % stops.length]
    }
    case 'pulse': {                        // 中心脉冲：从中心炸开再收回
      const hi = Math.ceil(n / 2)
      const r = Math.min(hi, Math.floor(t * (2 * hi - 1)) + 1)
      const rr = r <= hi ? r : 2 * hi - r   // 先增后减
      return idx >= hi - rr && idx < hi + rr ? stops[0] : [0, 0, 0]
    }
    case 'fire': {                         // 火苗：确定性伪噪声逐珠抖动（与后端同式）
      const k = Math.floor(t * 16)
      const n1 = Math.sin(2.399 * idx + 2 * Math.PI * k / 16)
      const n2 = Math.sin(1.7 * idx + 2.4 + 2 * Math.PI * 3 * k / 16)
      const s = 0.3 + 0.7 * ((n1 * n2 + 1) / 2)
      return stops[0].map(v => v * s)
    }
    case 'auroraflow': {                   // 呼吸流光：色相流动+快起慢落+行进高光带
      const m = Math.max(2, stops.length)
      const e = t < 0.3 ? t / 0.3 : 1 - (t - 0.3) / 0.7
      const glow = 0.35 + 0.65 * e
      const band = t * n
      const x = (idx / n + t) % 1 * m
      const j = Math.floor(x) % m
      const base = mix(stops[j], stops[(j + 1) % m], x - Math.floor(x))
      const dd = Math.min(Math.abs(idx - band), Math.abs(idx - band + n), Math.abs(idx - band - n))
      const hl = 1 + 0.6 * Math.exp(-((dd / 1.5) ** 2))
      return base.map(v => Math.min(255, v * glow * hl))
    }
    case 'typewriter': {                   // 打字机：逐珠铺满后末珠闪两下再熄
      const seq = [...Array(n).keys()].map(x => x + 1).concat([n - 1, n, n - 1, n, 0])
      const litN = seq[Math.min(seq.length - 1, Math.floor(t * seq.length))]
      return idx < litN ? stops[0] : [0, 0, 0]
    }
    case 'rainbow':
      return hslToRgb(((idx / n) + t) % 1 * 360, 1, 0.55)
    case 'aurora': {                       // 空间渐变流动 + 全局正弦明暗
      const m = Math.max(2, stops.length)
      const u = (idx / n + t) % 1 * m
      const j = Math.floor(u) % m
      const glow = 0.55 + 0.45 * Math.sin(t * Math.PI * 2)
      return mix(stops[j], stops[(j + 1) % m], u - Math.floor(u)).map(v => v * glow)
    }
    default:
      return stops[0]
  }
}

function hslToRgb(h: number, s: number, l: number): number[] {
  const f = (n: number) => {
    const k = (n + h / 30) % 12
    const a = s * Math.min(l, 1 - l)
    return Math.round(255 * (l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1))))
  }
  return [f(0), f(8), f(4)]
}

// ---- 实时预览：大号手柄 + rgb_num 颗灯珠逐帧上色 ----
function PadPreview({ mode, colors, brightness, period, rgbNum, frames, loopMs }: {
  mode: Mode; colors: number[][]; brightness: number; period: number; rgbNum: number
  frames?: number[][] | null; loopMs?: number      // 有帧表时直接回放设备原文（外部灯效）
}) {
  const [t, setT] = useState(0)
  // 帧驱动预览：与设备同模型——每帧驻留 loop_time，帧数与写入灯表的帧表一致。
  // 预览播的就是设备会播的那串帧、那个节奏（不再自造"整圈固定时长"）。
  const steps = frames?.length ? frames.length : stepsFor(mode, rgbNum)
  useEffect(() => {
    const iv = frames?.length
      ? Math.max(30, loopMs ?? 300)
      : Math.max(30, period * MS_PER_LT)
    const id = setInterval(() => setT(v => (v + 1 / steps) % 1), iv)
    return () => clearInterval(id)
  }, [period, mode, steps, loopMs, frames])

  const lit = mode !== 'off'
  const glow = lit ? 0.25 + 0.75 * (brightness / 255) : 0
  const dots = useMemo(() => Array.from({ length: rgbNum }, (_, i) => {
    const u = i / Math.max(1, rgbNum - 1)
    return { x: 90 + u * 180, y: 118 + Math.sin(u * Math.PI) * 16 }
  }), [rgbNum])

  return (
    <div className="relative flex items-center justify-center overflow-hidden rounded-xl border border-border-soft bg-[#0a0a12] p-2">
      <div className="pointer-events-none absolute inset-0 transition-colors duration-500"
        style={{ background: `radial-gradient(ellipse 70% 60% at 50% 65%, rgba(${(colors[0] ?? [0, 170, 255]).map(Math.round).join(',')},${0.16 * glow}), transparent 70%)` }} />
      <svg viewBox="0 0 360 170" className="relative w-full max-w-md">
        <g fill="#101018" stroke="#23233a" strokeWidth="2">
          <rect x="70" y="52" width="220" height="52" rx="26" />
          <ellipse cx="86" cy="98" rx="42" ry="46" />
          <ellipse cx="274" cy="98" rx="42" ry="46" />
        </g>
        <circle cx="86" cy="98" r="16" fill="#161624" stroke="#23233a" />
        <circle cx="274" cy="98" r="16" fill="#161624" stroke="#23233a" />
        {[[196, 66], [212, 60], [228, 66], [212, 76]].map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r="5" fill="#161624" stroke="#23233a" />
        ))}
        {dots.map((d, i) => {
          const k = Math.floor(t * steps) % steps
          const f = frames?.length ? frames[k] : null
          const c = f ? [f[i * 3], f[i * 3 + 1], f[i * 3 + 2]] : ledColor(mode, colors, i, rgbNum, t)
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

/** 风格卡迷你预览：自走帧（节奏按 period 缩放），预览同款帧算法 */
function MiniStrip({ mode, colors, period = 10 }: { mode: Mode; colors: number[][]; period?: number }) {
  const [t, setT] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setT(v => (v + 1 / 24) % 1), Math.max(60, period * MS_PER_LT))
    return () => clearInterval(id)
  }, [period])
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
  const [styleId, setStyleId] = useState('red-breath')
  const [mode, setMode] = useState<Mode>('breath')
  const [colors, setColors] = useState<number[][]>([[255, 30, 30]])
  const [brightness, setBrightness] = useState(128)
  const [period, setPeriod] = useState(10)
  const [sync, setSync] = useState<Sync>('idle')
  const [syncMsg, setSyncMsg] = useState('')
  const [devFrames, setDevFrames] = useState<number[][] | null>(null)
  const [devLoop, setDevLoop] = useState(300)
  const [foreign, setForeign] = useState(false)

  // ---- 自动写入引擎：650ms 防抖 + 串行队列（写一次 ~1-2s，绝不并发打手柄） ----
  const touched = useRef(false)          // 首次进页不回写：状态以设备为准
  const timer = useRef(0)
  const writing = useRef(false)

  const refresh = () => api.ledConfig().then(r => setBean(r.bean)).catch(() => {})

  // 进页回读：设备当前灯表 → 识别灯效+配色 → 还原上次设置（touched 未置位前绝不回写）。
  // 库内命中 → 点亮那张卡；模式认得但颜色改过 → 落「自定义」；认不出 → 外部灯效只读展示。
  useEffect(() => {
    api.ledConfig().then(r => {
      setBean(r.bean)
      if (r.frames_b64 && r.bean && r.bean.rgb_num > 0) {
        const raw = atob(r.frames_b64)
        const fsize = r.bean.rgb_num * 3
        const fs: number[][] = []
        for (let o = 0; o + fsize <= raw.length && fs.length < 255; o += fsize) {
          const f: number[] = []
          for (let i = 0; i < fsize; i++) f.push(raw.charCodeAt(o + i))
          fs.push(f)
        }
        if (fs.length) { setDevFrames(fs); setDevLoop(Math.max(30, r.bean.loop_time * MS_PER_LT)) }
      }
      const d: LedDetect | null | undefined = r.detect
      if (touched.current || !d || !r.bean) return
      setBrightness(r.bean.brightness || 128)
      setPeriod(r.bean.loop_time || 10)
      if (!d.known) {                                    // 外部灯效（官方/第三方）：只读
        setForeign(true)
        setStyleId('foreign')
        return
      }
      setForeign(false)
      setMode(d.mode as Mode)
      if (d.mode === 'rainbow') setColors([])
      else if (d.colors.length) setColors(d.colors)
      const m = d.mode === 'off' ? OFF_STYLE
        : LIB.find(s => s.mode === d.mode && s.colors.length === d.colors.length &&
            s.colors.every((c, i) => c.every((v, j) => Math.abs(v - d.colors[i][j]) <= 12)))
      setStyleId(m ? m.id : 'custom')
    }).catch(() => {})
  }, [])

  const runSync = async () => {
    if (writing.current) { scheduleSync(); return }      // 写盘中又改了 → 写完再补一轮
    if (mode !== 'off' && mode !== 'rainbow' &&
        colors.length < (mode === 'gradient' || mode === 'duosweep' || mode === 'chase' ? 2 : 1)) {
      setSync('idle'); return
    }
    writing.current = true
    setSync('writing')
    try {
      await api.ledApply(mode, mode === 'off' ? [] : colors, mode === 'off' ? undefined : brightness, period)
      setSync('ok')
      setForeign(false)
      setDevFrames(null)
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

  // ---- 交互 ----
  const pickStyle = (s: Style) => {                      // 选库内灯效：整套上身
    touched.current = true
    setForeign(false)
    setDevFrames(null)
    setStyleId(s.id); setMode(s.mode); setColors(s.colors)
    if (s.period) setPeriod(s.period)
  }
  const edit = (fn: () => void) => {                     // 手动改任何东西 → 转自定义
    touched.current = true
    fn()
    setStyleId('custom')
  }
  const setColor = (i: number, v: string) => edit(() => {
    const rgb = [parseInt(v.slice(1, 3), 16), parseInt(v.slice(3, 5), 16), parseInt(v.slice(5, 7), 16)]
    setColors(cs => cs.map((c, j) => (j === i ? rgb : c)))
  })
  const addColor = () => edit(() => setColors(cs => [...cs, [255, 255, 255]]))
  const delColor = () => edit(() => setColors(cs => cs.slice(0, -1)))
  const randomStyle = () => edit(() => {                 // 只随机配色，不动灯效/亮度/速度
    const h = Math.random() * 360
    const mk = (dh: number) => hslToRgb((h + dh) % 360, 0.85, 0.55)
    const n = multiColor ? Math.max(2, colors.length) : 1
    setColors(Array.from({ length: n }, (_, i) => mk(i * 137.5)))   // 黄金角散布，和谐配色
  })
  const restore = async () => {
    setSync('writing')
    setForeign(false)
    setDevFrames(null)
    try { await api.ledRestore(); setSync('ok'); refresh() } catch (e) { setSync('err'); setSyncMsg((e as Error).message) }
  }

  const SYNC_UI: Record<Sync, { text: string; cls: string }> = {
    idle: { text: '待机', cls: 'border-border-soft bg-white/5 text-text-low' },
    queued: { text: '等待改动停止…', cls: 'border-warn/40 bg-warn/10 text-warn' },
    writing: { text: '写入灯表…', cls: 'border-accent/40 bg-accent/10 text-accent' },
    ok: { text: '已同步到灯表', cls: 'border-ok/40 bg-ok/10 text-ok' },
    err: { text: `同步失败：${syncMsg}`, cls: 'border-err/40 bg-err/10 text-err' },
  }
  const su = SYNC_UI[sync]

  const needsColors = mode !== 'off' && mode !== 'rainbow'
  const multiColor = mode === 'gradient' || mode === 'flow' || mode === 'aurora' || mode === 'auroraflow'
  const twoColor = mode === 'duosweep' || mode === 'chase'   // 固定两色：无加减钮
  const curStyle = styleId === 'custom'
    ? { ...CUSTOM, mode, colors: needsColors ? colors : [] }
    : styleId === 'foreign'
      ? { id: 'foreign', name: '外部灯效', mode, colors: needsColors ? colors : [] }
      : styleId === 'off' ? OFF_STYLE : LIB.find(s => s.id === styleId) ?? CUSTOM

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      {/* 顶栏：标题 + 同步状态 */}
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[15px] font-semibold text-text-hi">灯光工坊</div>
          <div className="text-[11px] text-text-low">灯效库选款式，配色随便改——所有调整自动写入手柄</div>
        </div>
        <div className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[11px] ${su.cls}`} data-sync={sync}>
          {sync === 'writing' && <Loader2 size={12} className="animate-spin" />}
          {sync === 'ok' && <Check size={12} />}
          {sync === 'err' && <TriangleAlert size={12} />}
          {su.text}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_300px]">
        {/* 左：预览台 + 编辑器 */}
        <div className="space-y-4">
          <PadPreview mode={mode} colors={colors} brightness={brightness} period={period}
            rgbNum={bean?.rgb_num ?? 10} frames={devFrames} loopMs={devLoop} />

          <div className="card space-y-4 p-4">
            {foreign && (
              <div className="flex items-start gap-2 rounded-lg border border-warn/30 bg-warn/10 p-2.5 text-[11px] leading-relaxed text-warn">
                <TriangleAlert size={13} className="mt-0.5 shrink-0" />
                <span>手柄当前是<b>外部灯效</b>（官方默认或第三方写入），灯效库未收录——预览直接回放设备帧表原文；从右边库中任选一款即可接管。</span>
              </div>
            )}
            <div>
              <div className="mb-2 flex items-center gap-2 text-[12px] text-text-mid">
                当前灯效
                <span className="tag border-accent/40 text-accent">{curStyle.name}</span>
                {styleId === 'custom' && <span className="text-[10px] text-text-low">（已基于预设修改）</span>}
              </div>

              {/* 配色槽位（彩虹不吃配色，藏起来防误导） */}
              {needsColors ? (
                <div className="flex flex-wrap items-center gap-2">
                  {(multiColor ? colors : twoColor ? colors.slice(0, 2) : colors.slice(0, 1)).map((c, i) => (
                    <label key={i} className="relative h-11 w-11 cursor-pointer overflow-hidden rounded-xl border-2 border-white/15 transition-transform hover:scale-105"
                      style={{ background: hex(c), boxShadow: `0 0 14px ${hex(c)}66` }}>
                      <input type="color" value={hex(c)} onChange={e => setColor(i, e.target.value)}
                        className="absolute inset-0 cursor-pointer opacity-0" />
                    </label>
                  ))}
                  {multiColor && colors.length < 5 && (
                    <button className="flex h-11 w-11 items-center justify-center rounded-xl border border-dashed border-border-soft text-text-low transition-colors hover:border-accent/50 hover:text-accent"
                      onClick={addColor} title="加一色（渐变/流光类可叠到 5 色）">+</button>
                  )}
                  {multiColor && colors.length > 2 && (
                    <button className="flex h-11 w-11 items-center justify-center rounded-xl border border-dashed border-border-soft text-text-low transition-colors hover:border-err/50 hover:text-err"
                      onClick={delColor} title="减一色">-</button>
                  )}
                  <button className="btn !px-3 !py-1.5 text-[12px]" onClick={randomStyle} title="只随机配色，当前灯效不变">
                    <Dices size={13} /> 随机配色
                  </button>
                </div>
              ) : (
                <div className="text-[11px] text-text-low">
                  {mode === 'rainbow' ? '彩虹循环自带全色相环，不吃配色' : '熄灯状态——从右边灯效库挑一个点亮'}
                </div>
              )}
            </div>

            {/* 亮度 / 节奏 */}
            {mode !== 'off' && (
              <div className="grid grid-cols-2 gap-4">
                <label className="text-[12px] text-text-mid">
                  亮度 <span className="font-mono text-accent">{brightness}</span>
                  <input type="range" min={1} max={255} value={brightness}
                    onChange={e => edit(() => setBrightness(+e.target.value))} className="mt-1 w-full accent-[#22d3ee]" />
                </label>
                <label className="text-[12px] text-text-mid">
                  速度 <span className="font-mono text-accent">{ltToSpeed(period)}</span>
                  <span className="ml-1 text-[10px] text-text-low">右快左慢</span>
                  <input type="range" min={1} max={60} value={ltToSpeed(period)}
                    onChange={e => edit(() => setPeriod(speedToLt(+e.target.value)))} className="mt-1 w-full accent-[#22d3ee]" />
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

        {/* 右：灯效库 + 设备操作 */}
        <div className="space-y-4">
          <div className="card p-4">
            <div className="mb-3 text-[13px] font-medium">灯效库</div>
            <div className="grid grid-cols-2 gap-2">
              {/* 自定义卡（编辑态实时预览） */}
              <button onClick={() => { }}
                className={`rounded-lg border p-2 text-left transition-all ${
                  styleId === 'custom' ? 'border-accent/50 bg-accent/10' : 'border-border-soft'}`}
                title="在左边改配色/参数后自动进入这里">
                <MiniStrip mode={curStyle.mode} colors={needsColors ? colors : []} period={period} />
                <div className={`text-[11px] ${styleId === 'custom' ? 'text-accent' : 'text-text-mid'}`}>自定义</div>
              </button>
              {/* 熄灯卡 */}
              <button onClick={() => pickStyle(OFF_STYLE)}
                className={`rounded-lg border p-2 text-left transition-all hover:border-warn/40 ${
                  styleId === 'off' ? 'border-warn/50 bg-warn/10' : 'border-border-soft'}`}>
                <MiniStrip mode="off" colors={[]} />
                <div className="text-[11px] text-text-mid">熄灯</div>
              </button>
              {LIB.map(s => (
                <button key={s.id} onClick={() => pickStyle(s)}
                  className={`rounded-lg border p-2 text-left transition-all hover:border-accent/40 ${
                    styleId === s.id ? 'border-accent/50 bg-accent/10' : 'border-border-soft'}`}>
                  <MiniStrip mode={s.mode} colors={s.colors} period={s.period} />
                  <div className={`text-[11px] ${styleId === s.id ? 'text-accent' : 'text-text-mid'}`}>{s.name}</div>
                </button>
              ))}
            </div>
          </div>

          <div className="card space-y-2 p-4">
            <div className="text-[13px] font-medium">设备操作</div>
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
