// 体验区面板共享辅助（ADR-029 F2 自 panels.tsx 拆出）：样式常量/行布局/闪烁消息/
// 错误提示/键表常量/曲线画布/面板级错误边界。
import { Component, useEffect, useRef, useState, type ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'

export const BTN = 'rounded-md border border-border-soft px-2 py-1 text-[11px] transition-colors hover:border-accent/40 hover:text-accent'
export const BTN_ACC = 'rounded-md border border-accent/40 bg-accent/10 px-2 py-1 text-[11px] text-accent transition-colors hover:bg-accent/20'
export const BTN_DANGER = 'rounded-md border border-red-500/40 bg-red-500/10 px-2 py-1 text-[11px] text-red-300 transition-colors hover:bg-red-500/20'

export function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <span className="w-24 shrink-0 text-text-low">{label}</span>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  )
}

export function useFlash(): [string, (ok: string, e?: unknown) => void] {
  const [msg, setMsg] = useState('')
  const flash = (ok: string, e?: unknown) => {
    const t = e ? `✗ ${e instanceof Error ? e.message : String(e)}` : ok
    setMsg(t)
    setTimeout(() => setMsg(''), 4000)
  }
  return [msg, flash]
}

export function Err({ e }: { e: string }) {
  if (!e) return null
  return <div className="flex items-center gap-1 text-[11px] text-amber-300"><AlertTriangle size={12} /> {e}</div>
}

// k5 键表 id ↔ 名（与后端 profile.APEX5_KEYS 同源）
export const KEY_NAMES: Record<number, string> = {
  0: '十字上', 1: '十字右', 2: '十字下', 3: '十字左', 4: 'A', 5: 'B', 6: '选择', 7: 'X', 8: 'Y',
  9: '开始', 10: 'LB', 11: 'RB', 12: 'LT', 13: 'RT', 14: 'L3', 15: 'R3', 18: 'M1', 19: 'M2',
  20: 'M3', 21: 'M4', 22: 'M5', 23: 'M6', 27: 'Home',
}
export const TARGET_NAMES: Record<number, string> = {
  255: '透传', 254: '键盘', 32: '宏', 0: '十字上', 1: '十字右', 2: '十字下', 3: '十字左',
  4: 'A', 5: 'B', 6: '选择', 7: 'X', 8: 'Y', 9: '开始', 10: 'LB', 11: 'RB', 12: 'LT', 13: 'RT',
  14: 'L3', 15: 'R3', 27: 'Home',
}
export const TURBO_MODES = ['关', '按住连发', '开关切换']

// ---- 摇杆曲线源形式（与后端 stick_nodes 同款，画图用） ----
function stickNodes(center: number, edge: number, p1: [number, number], p2: [number, number]) {
  const start: [number, number] = center > 0 ? [center, 0] : [0, -center]
  const end: [number, number] = edge > 0 ? [100 - edge, 100] : [100, 100 + edge]
  const scale = 100 / 127
  const span = end[0] - start[0]
  if (span <= 0) return [start, end]
  const inner = (p: [number, number]): [number, number] =>
    [start[0] + (span * (p[0] * scale)) / 100, p[1] * scale]
  return [start, inner(p1), inner(p2), end]
}

export function CurveCanvas({ center, edge, p1, p2, bank }: {
  center: number; edge: number; p1: [number, number]; p2: [number, number]; bank: number[]
}) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const cv = ref.current
    if (!cv) return
    const g = cv.getContext('2d')
    if (!g) return
    const W = cv.width, H = cv.height
    g.clearRect(0, 0, W, H)
    g.strokeStyle = 'rgba(255,255,255,0.1)'
    g.strokeRect(0.5, 0.5, W - 1, H - 1)
    const X = (x: number) => (x / 100) * (W - 8) + 4
    const Y = (y: number) => H - 4 - (y / 100) * (H - 8)
    // 源形式折线
    const nodes = stickNodes(center, edge, p1, p2)
    g.strokeStyle = '#67e8f9'
    g.beginPath()
    nodes.forEach((n, i) => (i ? g.lineTo(X(n[0]), Y(n[1])) : g.moveTo(X(n[0]), Y(n[1]))))
    g.stroke()
    // bank 采样点（固件真正播的九点，值-50 → 0..100）
    g.fillStyle = '#fbbf24'
    bank.forEach((b, i) => {
      const x = (100 * i) / (bank.length - 1)
      const y = Math.max(-50, Math.min(100, b))
      g.fillRect(X(x) - 2, Y(y) - 2, 4, 4)
    })
  }, [center, edge, p1, p2, bank])
  return <canvas ref={ref} width={220} height={110} className="rounded border border-border-soft" />
}

export function NoDev() {
  return <div className="text-[11px] text-text-low">需要真机连接（右上角连接手柄后使用）。</div>
}

// 面板级错误边界：单个面板渲染炸了只显示自己的错误，不连坐整页
// （此前页面级 ErrorBoundary 一接管，用户看到的就是「点了展不开」，2026-09-20）
class PanelBoundary extends Component<{ children: ReactNode }, { err: string | null }> {
  state = { err: null as string | null }
  static getDerivedStateFromError(e: Error) { return { err: String(e?.message ?? e) } }
  render() {
    return this.state.err
      ? <div className="flex items-center gap-1 text-[11px] text-red-300"><AlertTriangle size={12} /> 面板出错：{this.state.err}</div>
      : this.props.children
  }
}
export const Safe = (C: React.FC): React.FC => props => (
  <PanelBoundary><C {...props} /></PanelBoundary>
)
