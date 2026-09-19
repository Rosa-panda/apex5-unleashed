import { useEffect, useState } from 'react'
import { Gamepad2, Play, Trash2, RefreshCw, Lock } from 'lucide-react'
import { api, type Preset } from '../api'

function describe(p: Preset): string {
  return p.actions.map((a) => {
    const s = a.side === 'left' ? 'LT' : a.side === 'right' ? 'RT' : a.side
    if (a.kind === 'trigger') return `${s}:${a.mode}`
    if (a.kind === 'grip') return `${s}:握把路由`
    if (a.kind === 'rumble') return '震动'
    return a.kind as string
  }).join(' + ')
}

export default function PresetLibrary() {
  const [data, setData] = useState<{ builtin: Preset[]; user: Preset[] }>({ builtin: [], user: [] })
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState('')

  const load = () => api.presets().then(setData).catch(() => {})
  useEffect(() => { load() }, [])

  const apply = async (p: Preset) => {
    setBusy(p.id)
    setMsg('')
    try {
      await api.applyPreset(p.id)
      setMsg(`✓ 已应用「${p.name}」`)
    } catch (e) {
      setMsg(`✗ 应用失败并已回滚：${(e as Error).message}`)
    }
    setBusy('')
  }

  const del = async (p: Preset) => {
    setBusy(p.id)
    try { await api.deletePreset(p.id) } catch { /* 忽略 */ }
    await load()
    setBusy('')
  }

  const Section = ({ title, list, isBuiltin }: { title: string; list: Preset[]; isBuiltin: boolean }) => (
    <div>
      <div className="mb-2 flex items-center gap-2 text-[12px] text-text-mid">
        {title} <span className="tag">{list.length}</span>
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {list.map((p) => (
          <div key={p.id} className="card group p-4 transition-colors hover:border-accent-dim">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="flex items-center gap-1.5 text-[13px] font-medium">
                  <Gamepad2 size={13} className="shrink-0 text-accent" />
                  <span className="truncate">{p.name}</span>
                  {isBuiltin && <Lock size={11} className="shrink-0 text-text-low" />}
                </div>
                <div className="mt-0.5 truncate font-mono text-[11px] text-text-low">{describe(p)}</div>
                {p.note && <div className="mt-1.5 text-[11px] leading-snug text-text-mid">{p.note}</div>}
              </div>
              <div className="flex shrink-0 gap-1">
                <button className="btn !px-2.5" disabled={busy === p.id}
                  onClick={() => apply(p)} title="事务式应用（失败自动回滚）">
                  <Play size={12} />
                </button>
                {!isBuiltin && (
                  <button className="btn btn-danger !px-2.5" disabled={busy === p.id}
                    onClick={() => del(p)} title="删除">
                    <Trash2 size={12} />
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
        {list.length === 0 && (
          <div className="card p-4 text-[12px] text-text-low">
            {isBuiltin ? '暂无' : '暂无自定义预设——去扳机实验室保存一个'}
          </div>
        )}
      </div>
    </div>
  )

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-center justify-between">
        <div className="text-[12px] text-text-mid">应用预设 = 清空旧效果 → 逐条下发 → 失败自动回滚</div>
        <button className="btn" onClick={load}><RefreshCw size={12} /> 刷新</button>
      </div>
      {msg && <div className="rounded-md border border-border-soft bg-card px-3 py-2 text-[12px]">{msg}</div>}
      <Section title="自定义预设" list={data.user} isBuiltin={false} />
      <Section title="内置预设" list={data.builtin} isBuiltin={true} />
    </div>
  )
}
