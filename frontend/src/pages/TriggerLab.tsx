import { useEffect, useMemo, useRef, useState } from 'react'
import { Crosshair, Eye, Save, Waves, Vibrate, Eraser } from 'lucide-react'
import { api, type EngineSnapshot } from '../api'

const MODE_META: Record<string, { label: string; desc: string }> = {
  normal: { label: 'Normal', desc: '原生线性，无附加力' },
  race: { label: 'Race 赛车', desc: '行程中段起阻尼渐增，模拟油门踏板' },
  sniper: { label: 'Sniper 狙击', desc: '推到触发点锁死（开镜），松手回弹' },
  recoil: { label: 'Recoil 后坐', desc: '扣到底触发一次冲击回弹' },
  lock: { label: 'Lock 锁定', desc: '推到触发点后卡住' },
  vibration: { label: 'Vibration 振动', desc: '扳机行程内振动反馈' },
}
const FIELD_LABEL: Record<string, string> = {
  stroke: '行程', resistance: '阻尼强度', match: '双侧同步',
  press: '触发点', strength: '力度', freq: '频率',
  recoil_stroke: '回弹行程',
}
const FIELD_IS_TOGGLE: Record<string, boolean> = { match: true }
const FIELD_DEFAULTS: Record<string, number> = {
  stroke: 150, resistance: 100, press: 60, strength: 150, freq: 20,
  recoil_stroke: 80, match: 1,
}

export default function TriggerLab({ snap }: { snap: EngineSnapshot | null }) {
  const [side, setSide] = useState<'left' | 'right' | 'both'>('right')
  const [mode, setMode] = useState('recoil')
  const [params, setParams] = useState<Record<string, number>>({})
  const [previewOn, setPreviewOn] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveName, setSaveName] = useState('')
  const previewTimer = useRef<number | undefined>(undefined)

  const fields = useMemo(() => {
    const table: Record<string, string[]> = {
      normal: [], race: ['stroke', 'resistance', 'match'],
      sniper: ['stroke', 'press', 'strength', 'freq', 'match'],
      recoil: ['stroke', 'recoil_stroke', 'strength', 'match'],
      lock: ['stroke', 'strength', 'match'],
      vibration: ['stroke', 'press', 'strength', 'freq', 'match'],
    }
    return table[mode] ?? []
  }, [mode])

  useEffect(() => {
    // 模式切换 → 补默认参数
    setParams(Object.fromEntries(
      fields.map((f) => [f, FIELD_DEFAULTS[f] ?? 100]),
    ))
  }, [mode])  // eslint-disable-line react-hooks/exhaustive-deps

  const sides = side === 'both' ? ['left', 'right'] : [side]

  const send = (apply: boolean) => {
    sides.forEach((s) => api.trigger(s, mode, params, apply).catch(() => {}))
  }

  // 预览模式：参数变化 50ms 防抖后热更新
  useEffect(() => {
    if (!previewOn) return
    if (previewTimer.current) clearTimeout(previewTimer.current)
    previewTimer.current = window.setTimeout(() => send(false), 50)
    return () => { if (previewTimer.current) clearTimeout(previewTimer.current) }
  }, [previewOn, mode, params])  // eslint-disable-line react-hooks/exhaustive-deps

  const cur = snap?.state.triggers[side === 'both' ? 'right' : side]

  const doSave = async () => {
    if (!saveName.trim()) return
    setSaving(true)
    try {
      await api.savePreset(saveName.trim(), `实验室导出 · ${MODE_META[mode].label}`,
        sides.map((s) => ({ kind: 'trigger', side: s, mode, params })))
      setSaveName('')
    } catch { /* 保存失败下次重试 */ }
    setSaving(false)
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      {/* 侧选择 + 模式选择 */}
      <div className="card p-5">
        <div className="mb-3 flex items-center gap-2 text-[12px] text-text-mid">
          <Crosshair size={14} className="text-accent" /> 目标与模式
        </div>
        <div className="mb-4 flex gap-2">
          {([['left', 'LT'], ['right', 'RT'], ['both', '双侧']] as const).map(([v, l]) => (
            <button key={v} onClick={() => setSide(v)}
              className={`btn ${side === v ? 'border-accent/60 text-accent' : ''}`}>
              {l}
            </button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
          {Object.entries(MODE_META).map(([m, meta]) => (
            <button key={m} onClick={() => setMode(m)}
              className={`rounded-lg border p-3 text-left transition-colors ${
                mode === m ? 'border-accent/60 bg-accent/8' : 'border-border-soft bg-[#161622] hover:border-accent-dim'
              }`}>
              <div className={`text-[13px] font-medium ${mode === m ? 'text-accent' : ''}`}>{meta.label}</div>
              <div className="mt-0.5 text-[11px] leading-snug text-text-low">{meta.desc}</div>
            </button>
          ))}
        </div>
      </div>

      {/* 参数 */}
      {fields.length > 0 && (
        <div className="card p-5">
          <div className="mb-4 text-[12px] text-text-mid">参数（官方协议钳位范围内实时校验）</div>
          <div className="space-y-4">
            {fields.map((f) => FIELD_IS_TOGGLE[f] ? (
              <div key={f} className="flex items-center justify-between">
                <span className="text-[13px]">{FIELD_LABEL[f]}</span>
                <button onClick={() => setParams({ ...params, [f]: params[f] ? 0 : 1 })}
                  className={`tag ${params[f] ? 'border-accent/50 text-accent' : ''}`}>
                  {params[f] ? '开' : '关'}
                </button>
              </div>
            ) : (
              <div key={f}>
                <div className="mb-1.5 flex items-center justify-between text-[13px]">
                  <span>{FIELD_LABEL[f]}</span>
                  <span className="tabular-nums text-accent">{params[f]}</span>
                </div>
                <input type="range" min={1} max={255} value={params[f] ?? 1}
                  onChange={(e) => setParams({ ...params, [f]: +e.target.value })}
                  className="w-full" />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 操作 */}
      <div className="card space-y-3 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <button className="btn btn-primary" onClick={() => send(true)}>
            <Waves size={13} /> 应用效果
          </button>
          <button className={`btn ${previewOn ? 'border-accent/60 text-accent' : ''}`}
            onClick={() => { setPreviewOn(!previewOn); if (previewOn) sides.forEach(s => api.clearTrigger(s)) }}>
            <Eye size={13} /> {previewOn ? '预览中（调参实时生效）' : '开启预览'}
          </button>
          <button className="btn" onClick={() => sides.forEach((s) => api.clearTrigger(s).catch(() => {}))}>
            <Eraser size={13} /> 清除为 Normal
          </button>
          <span className="ml-auto text-[11px] text-text-low">
            当前账本：{sides.map((s) => `${s === 'left' ? 'LT' : 'RT'}=${snap?.state.triggers[s as 'left' | 'right']?.mode ?? 'normal'}`).join(' · ')}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t border-border-soft pt-3">
          <input
            value={saveName} onChange={(e) => setSaveName(e.target.value)}
            placeholder="当前参数存为预设…"
            className="w-48 rounded-md border border-border-soft bg-[#0d0d14] px-3 py-1.5 text-[12px] outline-none focus:border-accent-dim"
          />
          <button className="btn" disabled={!saveName.trim() || saving} onClick={doSave}>
            <Save size={13} /> {saving ? '保存中…' : '保存'}
          </button>
          <div className="ml-auto flex gap-2">
            <button className="btn" onClick={() => api.pulse().catch(() => {})}>
              <Vibrate size={13} /> 震动测试
            </button>
            <button className="btn" onClick={() => api.sine(3, 3, 220).catch(() => {})}>
              <Waves size={13} /> 正弦扫频 3s
            </button>
          </div>
        </div>
      </div>

      {cur && (
        <div className="text-center text-[11px] text-text-low">
          最近应用：{cur.mode} · 来源 {cur.source} · {cur.applied_at}
        </div>
      )}
    </div>
  )
}
