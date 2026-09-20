// 灯光页（ADR-018）：写表驻留协议，效果 PC 侧展开 → 0xA8/0xA9 写入 → 读回自校验
import { useEffect, useState } from 'react'
import { Lightbulb, Moon, Palette, RotateCcw, Save } from 'lucide-react'
import { api, type LedBean } from '../api'

type Mode = 'off' | 'on' | 'breath' | 'gradient' | 'flow'

const MODES: Array<{ id: Mode; label: string; minColors: number }> = [
  { id: 'off', label: '关闭', minColors: 0 },
  { id: 'on', label: '常亮', minColors: 1 },
  { id: 'breath', label: '呼吸', minColors: 1 },
  { id: 'gradient', label: '渐变', minColors: 2 },
  { id: 'flow', label: '流光', minColors: 1 },
]
const PRESETS: Array<{ name: string; colors: number[][]; mode: Mode }> = [
  { name: '冰蓝常亮', colors: [[0, 170, 255]], mode: 'on' },
  { name: '红色呼吸', colors: [[255, 30, 30]], mode: 'breath' },
  { name: '赛博渐变', colors: [[255, 0, 200], [0, 220, 255]], mode: 'gradient' },
  { name: '彩虹流光', colors: [[255, 0, 0], [255, 200, 0], [0, 255, 60], [0, 200, 255], [120, 0, 255]], mode: 'flow' },
]

export default function Lights() {
  const [bean, setBean] = useState<LedBean | null>(null)
  const [mode, setMode] = useState<Mode>('breath')
  const [colors, setColors] = useState<number[][]>([[0, 170, 255]])
  const [brightness, setBrightness] = useState(128)
  const [period, setPeriod] = useState(10)
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  const refresh = () => api.ledConfig().then(r => setBean(r.bean)).catch(() => {})
  useEffect(() => { refresh() }, [])

  const spec = MODES.find(m => m.id === mode)!
  const ready = spec.minColors === 0 || colors.length >= spec.minColors

  const apply = async (m = mode, cs = colors) => {
    setBusy(true); setMsg('写入中…')
    try {
      await api.ledApply(m, cs, m === 'off' ? undefined : brightness, period)
      setMsg('✓ 已写入（读回校验通过）')
      refresh()
    } catch (e) { setMsg(`✗ ${(e as Error).message}`) }
    setBusy(false)
  }

  const backup = async () => {
    try {
      await api.ledBackup(); setMsg('✓ 当前灯表已备份（含官方彩虹，可随时恢复）')
    } catch (e) { setMsg(`✗ ${(e as Error).message}`) }
  }
  const restore = async () => {
    setBusy(true); setMsg('恢复中…')
    try { await api.ledRestore(); setMsg('✓ 已恢复备份灯表') } catch (e) { setMsg(`✗ ${(e as Error).message}`) }
    setBusy(false)
  }

  const setColor = (i: number, v: string) => {
    const rgb = [parseInt(v.slice(1, 3), 16), parseInt(v.slice(3, 5), 16), parseInt(v.slice(5, 7), 16)]
    setColors(cs => cs.map((c, j) => (j === i ? rgb : c)))
  }
  const hex = (c: number[]) => '#' + c.map(v => v.toString(16).padStart(2, '0')).join('')

  return (
    <div className="max-w-3xl space-y-4">
      <div className="card p-4">
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2 text-[14px] font-medium"><Lightbulb size={15} className="text-accent" /> 灯光</div>
          {bean && (
            <div className="font-mono text-[11px] text-text-low">
              V{bean.version} · {bean.rgb_num} 灯珠 · 亮度 {bean.brightness} · 帧距 {bean.loop_time}
            </div>
          )}
        </div>

        {/* 模式 */}
        <div className="mb-4 flex gap-1.5">
          {MODES.map(m => (
            <button key={m.id} onClick={() => setMode(m.id)}
              className={`rounded-lg px-3 py-1.5 text-[12px] transition-colors ${
                mode === m.id ? 'bg-accent/15 text-accent' : 'text-text-mid hover:bg-white/4'}`}>
              {m.label}
            </button>
          ))}
        </div>

        {/* 颜色 */}
        {mode !== 'off' && (
          <div className="mb-4">
            <div className="mb-2 flex items-center gap-2 text-[12px] text-text-mid">
              <Palette size={12} /> 颜色
              {spec.minColors > 1 && colors.length < spec.minColors && (
                <span className="text-warn">（{spec.label}至少 {spec.minColors} 色）</span>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {colors.map((c, i) => (
                <input key={i} type="color" value={hex(c)} onChange={e => setColor(i, e.target.value)}
                  className="h-8 w-10 cursor-pointer rounded border border-border-soft bg-[#0d0d14]" />
              ))}
              {colors.length < 5 && (
                <button className="btn !px-2 !py-1 text-[11px]"
                  onClick={() => setColors(cs => [...cs, [255, 255, 255]])}>+ 加色</button>
              )}
              {colors.length > 1 && (
                <button className="btn !px-2 !py-1 text-[11px]"
                  onClick={() => setColors(cs => cs.slice(0, -1))}>- 减色</button>
              )}
            </div>
          </div>
        )}

        {/* 亮度 / 速度 */}
        {mode !== 'off' && (
          <div className="mb-4 grid grid-cols-2 gap-4">
            <label className="text-[12px] text-text-mid">
              亮度 <span className="font-mono text-accent">{brightness}</span>
              <input type="range" min={1} max={255} value={brightness}
                onChange={e => setBrightness(+e.target.value)} className="mt-1 w-full accent-[#22d3ee]" />
            </label>
            <label className="text-[12px] text-text-mid">
              帧距 <span className="font-mono text-accent">{period}</span>
              <input type="range" min={1} max={60} value={period}
                onChange={e => setPeriod(+e.target.value)} className="mt-1 w-full accent-[#22d3ee]" />
            </label>
          </div>
        )}

        <div className="flex items-center gap-2">
          <button className="btn btn-primary" disabled={busy || !ready} onClick={() => apply()}>
            <Save size={13} /> 写入灯表
          </button>
          <button className="btn" disabled={busy} onClick={backup} title="把当前灯表存盘（写入前先备份一次）">
            <Save size={13} /> 备份当前
          </button>
          <button className="btn" disabled={busy} onClick={restore} title="写回备份的灯表（官方彩虹等）">
            <RotateCcw size={13} /> 恢复备份
          </button>
          {msg && <span className="text-[12px] text-text-mid">{msg}</span>}
        </div>
      </div>

      {/* 快捷预设 */}
      <div className="card p-4">
        <div className="mb-3 text-[13px] font-medium">快捷预设</div>
        <div className="flex flex-wrap gap-2">
          <button disabled={busy} onClick={() => { setMode('off'); apply('off', []) }}
            className="btn !px-3 !py-1.5 text-[12px] border-warn/50 text-warn"
            title="灯表写全黑 + led_mode=0，整柄熄灯；想开回来到上方模式选「常亮」即可">
            <Moon size={12} /> 一键关灯
          </button>
          {PRESETS.map(p => (
            <button key={p.name} disabled={busy} onClick={() => { setMode(p.mode); setColors(p.colors); apply(p.mode, p.colors) }}
              className="btn !px-3 !py-1.5 text-[12px]">
              <span className="flex gap-0.5">
                {p.colors.map((c, i) => (
                  <span key={i} className="h-3 w-3 rounded-full border border-white/20" style={{ background: hex(c) }} />
                ))}
              </span>
              {p.name}
            </button>
          ))}
        </div>
        <div className="mt-3 text-[11px] text-text-low">
          写入即驻留（设备端循环播放，重启手柄仍生效）；首次使用建议先点一次「恢复备份」生成官方灯表备份。
        </div>
      </div>
    </div>
  )
}
