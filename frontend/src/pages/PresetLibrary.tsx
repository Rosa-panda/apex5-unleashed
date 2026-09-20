import { useEffect, useMemo, useState } from 'react'
import { Gamepad2, Play, Trash2, RefreshCw, Lock, Zap, Link2, FlaskConical } from 'lucide-react'
import { api, type EngineSnapshot, type Preset } from '../api'

function describe(p: Preset): string {
  return p.actions.map((a) => {
    const s = a.side === 'left' ? 'LT' : a.side === 'right' ? 'RT' : a.side
    if (a.kind === 'trigger') return `${s}:${a.mode}`
    if (a.kind === 'grip') return `${s}:握把路由`
    if (a.kind === 'rumble') return '震动'
    return a.kind as string
  }).join(' + ')
}

export default function PresetLibrary({ snap }: { snap: EngineSnapshot | null }) {
  const [data, setData] = useState<{ builtin: Preset[]; user: Preset[] }>({ builtin: [], user: [] })
  const [linked, setLinked] = useState<Record<string, string[]>>({})   // preset_id → 游戏名列表
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState('')

  const load = () => {
    api.presets().then(setData).catch(() => {})
    api.games().then((g) => {
      const m: Record<string, string[]> = {}
      for (const game of [...g.user, ...g.builtin]) {
        if (game.preset_id) (m[game.preset_id] ??= []).push(game.name)
      }
      setLinked(m)
    }).catch(() => {})
  }
  useEffect(() => { load() }, [])

  // 生效判定：扳机/握把账本的 source 是 "preset:预设名"（应用或自动切换写入）
  const activePresetName = useMemo(() => {
    const src = snap?.state.triggers.left?.source ?? snap?.state.triggers.right?.source
      ?? snap?.state.gripBind.left?.source ?? snap?.state.gripBind.right?.source ?? ''
    return src.startsWith('preset:') ? src.slice('preset:'.length) : null
  }, [snap])

  const apply = async (p: Preset) => {
    setBusy(p.id)
    setMsg('')
    try {
      await api.applyPreset(p.id)
      setMsg(`✓ 已应用「${p.name}」——手上现在就能感受到`)
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
        {list.map((p) => {
          const active = activePresetName === p.name
          const games = linked[p.id] ?? []
          return (
            <div key={p.id} className={`card group p-4 transition-colors ${active ? 'border-accent/60' : 'hover:border-accent-dim'}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 text-[13px] font-medium">
                    <Gamepad2 size={13} className="shrink-0 text-accent" />
                    <span className="truncate">{p.name}</span>
                    {isBuiltin && <Lock size={11} className="shrink-0 text-text-low" />}
                    {active && (
                      <span className="tag shrink-0 border-accent/50 !text-accent" title="当前正写入手柄固件的预设">
                        <Zap size={9} className="mr-0.5" />生效中
                      </span>
                    )}
                  </div>
                  <div className="mt-0.5 truncate font-mono text-[11px] text-text-low">{describe(p)}</div>
                  {p.note && <div className="mt-1.5 text-[11px] leading-snug text-text-mid">{p.note}</div>}
                  <div className="mt-1.5 flex items-center gap-1 text-[11px] text-text-low" title="游戏库里绑定本预设的游戏：进游戏自动套用，切出自动解绑">
                    <Link2 size={10} />
                    {games.length
                      ? <span>已绑定 {games.length} 款：{games.slice(0, 3).join('、')}{games.length > 3 ? ' 等' : ''}</span>
                      : <span>未绑定游戏（可去游戏库绑定，或点 ▶ 手动套用）</span>}
                  </div>
                </div>
                <div className="flex shrink-0 gap-1">
                  <button className={`btn !px-2.5 ${active ? 'border-accent/60 text-accent' : ''}`} disabled={busy === p.id}
                    onClick={() => apply(p)} title={active ? '正在生效' : '立即套用到手柄（失败自动回滚）'}>
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
          )
        })}
        {list.length === 0 && (
          <div className="card p-4 text-[12px] text-text-low">
            {isBuiltin ? '暂无' : '暂无自定义预设——去扳机实验室调好参数保存一个'}
          </div>
        )}
      </div>
    </div>
  )

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="card flex items-start gap-3 p-4 text-[12px] leading-relaxed text-text-mid">
        <FlaskConical size={16} className="mt-0.5 shrink-0 text-accent" />
        <div>
          <span className="text-text-hi">预设</span> = 一套打包好的扳机/震动手感配置（LT/RT 模式 + 参数 + 握把路由）。
          生效的两条路：<span className="text-accent">① 点 ▶ 立即套用</span>（马上写入手柄，手上可感）；
          <span className="text-accent">② 在游戏库绑定到游戏</span>，切进该游戏自动套用、切出自动恢复。
          当前生效的预设会标<span className="text-accent">「生效中」</span>，侧栏设备卡也能看到。
        </div>
      </div>
      <div className="flex items-center justify-between">
        <div className="text-[12px] text-text-mid">{activePresetName
          ? <span className="text-accent">当前生效：{activePresetName}</span>
          : '当前无预设生效（标准模式）'}</div>
        <button className="btn" onClick={load}><RefreshCw size={12} /> 刷新</button>
      </div>
      {msg && <div className="rounded-md border border-border-soft bg-card px-3 py-2 text-[12px]">{msg}</div>}
      <Section title="自定义预设" list={data.user} isBuiltin={false} />
      <Section title="内置预设" list={data.builtin} isBuiltin={true} />
    </div>
  )
}
