import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { Crosshair, Eye, Save, Waves, Vibrate, Eraser, FlaskConical } from 'lucide-react'
import { api, type EngineSnapshot } from '../api'
import { friendlySource } from './Overview'

const MODE_META: Record<string, { label: string; desc: string }> = {
  normal: { label: 'Normal 原生', desc: '无附加力，恢复手柄出厂手感' },
  race: { label: 'Race 赛车', desc: '行程中段起阻力渐增，模拟油门/刹车踏板' },
  sniper: { label: 'Sniper 狙击', desc: '推到触发点前有阻力，到位瞬间松脱——二段扳机/开镜手感' },
  recoil: { label: 'Recoil 后坐力', desc: '扣到触发点产生一次回弹冲击——开枪后坐手感' },
  lock: { label: 'Lock 锁定', desc: '推到触发点后卡住，松手才回弹' },
  vibration: { label: 'Vibration 振动', desc: '扳机行程内持续振动，打击感/机械感' },
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
  // 字段表从后端拉（/api/modes 即协议真相）——写死会跟协议漂移（2026-09-20 实踩：
  // 模式勘误交换后前端旧表错位，调参发错字段）
  const [modeFields, setModeFields] = useState<Record<string, string[]>>({})
  const previewTimer = useRef<number | undefined>(undefined)

  useEffect(() => {
    api.modes().then((m: { trigger: Record<string, string[]> }) => setModeFields(m.trigger)).catch(() => {})
  }, [])

  const fields = useMemo(() => modeFields[mode] ?? [], [modeFields, mode])

  useEffect(() => {
    // 模式切换或字段表异步到位 → 补默认参数（依赖 fields 而非 mode：
    // 2026-09-22 实踩：字段表晚于首帧到达时 effect 不重跑，params 恒空显示全 0）
    setParams(Object.fromEntries(
      fields.map((f) => [f, FIELD_DEFAULTS[f] ?? 100]),
    ))
  }, [fields])

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
      await api.savePreset(saveName.trim(), `实验室导出 · ${MODE_META[mode]?.label ?? mode}`,
        sides.map((s) => ({ kind: 'trigger', side: s, mode, params })))
      setSaveName('')
    } catch { /* 保存失败下次重试 */ }
    setSaving(false)
  }

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      {/* 引导：一句话 + 悬浮详情 */}
      <div
        className="card cursor-help p-3 text-[12px] leading-relaxed text-text-mid"
        title="流程：选模式 → 拖参数 → 点「应用效果」手上立刻感受；「开启预览」后拖动滑块实时生效。调到满意起名保存为预设，可在游戏库绑定到游戏自动套用。改的是手柄固件里的扳机效果，软件退出前会自动复位，放心试。"
      >
        <FlaskConical size={13} className="mr-1.5 inline text-text-low" />
        选模式 → 拖参数 → 应用 · 悬停看玩法
      </div>

      {/* 侧选择 + 模式选择（左栏）/ 参数与执行（右栏）——调参工作台双区动线 */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="card p-5 lg:col-span-5">
          <div className="mb-3 flex items-center gap-2 text-[12px] text-text-mid">
            <Crosshair size={14} className="text-text-mid" /> 目标与模式
          </div>
          <div className="mb-4 flex items-center gap-2">
            <span className="text-[12px] text-text-low">扳机：</span>
            <div className="segmented">
              {([['left', 'LT'], ['right', 'RT'], ['both', '双侧']] as const).map(([v, l]) => (
                <button key={v} onClick={() => setSide(v)} className={side === v ? 'on' : ''}>
                  {l}
                </button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
            {Object.entries(MODE_META).map(([m, meta]) => (
              <button key={m} onClick={() => setMode(m)}
                className={`rounded-xl border p-3 text-left transition-colors ${
                  mode === m ? 'card-selected text-text-hi' : 'card-hover text-text-mid'
                }`}>
                <div className={`text-[13px] font-medium ${mode === m ? 'text-accent' : ''}`}>{meta.label}</div>
                <div className="mt-0.5 text-[11px] leading-snug text-text-low">{meta.desc}</div>
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-4 lg:col-span-7">
          {/* 参数 */}
          {fields.length > 0 && (
            <div className="card p-5">
              <div className="mb-4 text-[12px] text-text-mid">参数（数值越大通常越强，官方协议范围内实时校验）</div>
              <div className="space-y-4">
                {fields.map((f) => FIELD_IS_TOGGLE[f] ? (
                  <div key={f} className="flex items-center justify-between">
                    <span className="text-[13px]">{FIELD_LABEL[f] ?? f}</span>
                    <button onClick={() => setParams({ ...params, [f]: params[f] ? 0 : 1 })}
                      className={`tag ${params[f] ? 'border-accent/50 text-accent' : ''}`}>
                      {params[f] ? '开' : '关'}
                    </button>
                  </div>
                ) : (
                  <div key={f}>
                    <div className="mb-1.5 flex items-center justify-between text-[13px]">
                      <span>{FIELD_LABEL[f] ?? f}</span>
                      <span className="rounded-md border border-border-soft/80 bg-inset px-2 py-0.5 font-mono text-[12px] tabular-nums text-text-hi">{params[f]}</span>
                    </div>
                    <input type="range" min={1} max={255} value={params[f] ?? 1}
                      onChange={(e) => setParams({ ...params, [f]: +e.target.value })}
                      style={{ '--fill': `${(((params[f] ?? 1) - 1) / 254) * 100}%` } as CSSProperties}
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
                <Eye size={13} /> {previewOn ? '预览中（拖滑块实时生效）' : '开启预览'}
              </button>
              <button className="btn" onClick={() => sides.forEach((s) => api.clearTrigger(s).catch(() => {}))}>
                <Eraser size={13} /> 清除为 Normal
              </button>
              <span className="ml-auto text-[11px] text-text-low">
                当前扳机：{sides.map((s) => `${s === 'left' ? 'LT' : 'RT'}=${snap?.state.triggers[s as 'left' | 'right']?.mode ?? 'normal'}`).join(' · ')}
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-2 border-t border-border-soft/70 pt-3">
              <input
                value={saveName} onChange={(e) => setSaveName(e.target.value)}
                placeholder="把当前参数存为预设（如：生化9 后坐力）…"
                className="input w-56 !text-[12px]"
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
              最近应用：{MODE_META[cur.mode]?.label ?? cur.mode} · 来源 {friendlySource(cur.source)} · {cur.applied_at}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
