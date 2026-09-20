// 游戏库（ADR-014 + ADR-017）：官方逐游戏适配 + 通用震动联动 + 自定义 exe
// 按几百款规模设计 —— 搜索(名称/英文名/进程名) + 筛选 + 封面卡 + 分段渲染
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Crosshair, Download, FolderOpen, MonitorPlay, Play, Plus, Search, Trash2, Link2, Zap } from 'lucide-react'
import { api, type Preset } from '../api'

interface VibParams { filter: number; scale: number; stroke: number; press: number; strength: number; freq: number }

interface GameProfile {
  id: string
  name: string
  en?: string
  exe: string[]
  preset_id: string
  note: string
  image?: string
  builtin: boolean
  source?: string
  vib?: VibParams | null
  official?: boolean
  mod_only?: boolean
  asb?: boolean
}

interface GamesResp {
  builtin: GameProfile[]
  user: GameProfile[]
  foreground: string | null
  autoswitch: boolean
  universal_vib: boolean
}

const PAGE = 24

export default function GameLibrary() {
  const [data, setData] = useState<GamesResp>({ builtin: [], user: [], foreground: null, autoswitch: true, universal_vib: false })
  const [presets, setPresets] = useState<Preset[]>([])
  const [q, setQ] = useState('')
  const [filter, setFilter] = useState<'all' | 'mine' | 'bound' | 'unbound' | 'vib'>('all')
  const [limit, setLimit] = useState(PAGE)
  const [msg, setMsg] = useState('')
  const [form, setForm] = useState({ name: '', exe: '', preset_id: '' })
  const [detail, setDetail] = useState<GameProfile | null>(null)
  const [pickFor, setPickFor] = useState<string | null>(null)   // 正在展开预设选择的卡片 id
  const fileRef = useRef<HTMLInputElement | null>(null)
  const exeTarget = useRef<string | null>(null)

  const load = useCallback(() => {
    api.games().then(setData).catch(() => {})
    api.presets().then(p => setPresets([...p.user, ...p.builtin])).catch(() => {})
  }, [])
  useEffect(() => { load(); const t = setInterval(load, 3000); return () => clearInterval(t) }, [load])

  const fg = data.foreground
  const presetName = (id: string) => presets.find(p => p.id === id)?.name ?? id
  const hit = (g: GameProfile) => !!fg && g.exe.some(e => e.replace(/\.exe$/i, '') === fg.replace(/\.exe$/i, ''))

  const pool = useMemo(() => [...data.user, ...data.builtin], [data])
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return pool.filter(g => {
      if (filter === 'mine' && g.builtin) return false
      if (filter === 'bound' && !(g.preset_id || g.vib)) return false
      if (filter === 'unbound' && (g.preset_id || g.vib)) return false
      if (filter === 'vib' && !g.vib) return false
      if (!needle) return true
      return g.name.toLowerCase().includes(needle)
        || (g.en ?? '').toLowerCase().includes(needle)
        || g.exe.some(e => e.includes(needle))
    })
  }, [pool, q, filter])

  // 搜索/筛选变化时重置渲染上限
  useEffect(() => { setLimit(PAGE) }, [q, filter])

  const apply = async (g: GameProfile) => {
    try {
      const r = await api.applyGame(g.id) as { result: { vib: boolean; preset: string } }
      setMsg(`✓ 已套用「${g.name}」${r.result.vib ? ' · 官方震动联动' : ''}${r.result.preset ? ` · ${presetName(r.result.preset)}` : ''}`)
    } catch (e) { setMsg(`✗ ${(e as Error).message}`) }
  }

  const link = async (g: GameProfile, preset_id: string) => {
    try { await api.linkGame(g.id, preset_id) } catch { /* 忽略 */ }
    load()
  }

  const del = async (g: GameProfile) => {
    try { await api.deleteGame(g.id) } catch { /* 忽略 */ }
    load()
  }

  const add = async () => {
    if (!form.name.trim() || !form.exe.trim()) return
    try {
      await api.saveGame({ name: form.name.trim(), exe: form.exe.split(/[,，\s]+/), preset_id: form.preset_id, note: '' })
      setForm({ name: '', exe: '', preset_id: '' })
      setMsg('✓ 已添加')
    } catch (e) { setMsg(`✗ ${(e as Error).message}`) }
    load()
  }

  const importOfficial = async () => {
    try {
      const r = await api.importOfficial() as { result: { imported: number; skipped: number } }
      setMsg(`✓ 已导入官方适配 ${r.result.imported} 款（跳过 ${r.result.skipped}）`)
    } catch (e) { setMsg(`✗ ${(e as Error).message}`) }
    load()
  }

  const toggleUniversal = async (on: boolean) => {
    setData(d => ({ ...d, universal_vib: on }))
    try { await api.setUniversalVib(on) } catch (e) { setMsg(`✗ ${(e as Error).message}`) }
  }

  // 自定义 exe：选文件 → 录进程名（特殊版本游戏定位）
  const pickExe = (g: GameProfile) => {
    exeTarget.current = g.id
    fileRef.current?.click()
  }
  const onExePicked = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    e.target.value = ''
    const gid = exeTarget.current
    if (!f || !gid) return
    try {
      await api.setGameExe(gid, [f.name])
      setMsg(`✓ 已定位到 ${f.name}（匹配键已更新）`)
    } catch (err) { setMsg(`✗ ${(err as Error).message}`) }
    load()
  }

  const Card = ({ g, picking, setPicking }: {
    g: GameProfile
    picking: boolean
    setPicking: (v: boolean) => void
  }) => {
    const active = hit(g)
    return (
      <div className={`card group overflow-hidden p-0 transition-colors ${active ? 'border-accent/60' : 'hover:border-accent-dim'}`}>
        {/* 封面条 */}
        <div className="relative h-16 w-full overflow-hidden bg-[#0d0d14]">
          {g.image
            ? <img src={g.image} alt="" loading="lazy" className="h-full w-full object-cover opacity-70 transition-opacity group-hover:opacity-100" />
            : <div className="flex h-full items-center justify-center text-text-low"><MonitorPlay size={18} /></div>}
          <div className="absolute inset-x-0 bottom-0 flex items-center gap-1.5 bg-gradient-to-t from-black/80 to-transparent px-3 pb-1 pt-4">
            <span className="truncate text-[13px] font-medium">{g.name}</span>
            {active && <span className="tag shrink-0 border-accent/50 !text-accent">正在玩</span>}
          </div>
          {g.vib && (
            <div className="absolute right-1.5 top-1.5 flex items-center gap-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-accent" title="官方手工调参：震动联动扳机">
              <Zap size={9} /> 官方适配
            </div>
          )}
          {g.asb && (
            <div className="absolute right-1.5 top-1.5 flex items-center gap-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-violet-300" title="原生支持 DualSense 自适应扳机（ASB/PCGamingWiki 清单）：事件级效果需 ASB 桥，本工具提供震动联动兜底">
              DS 原生
            </div>
          )}
          {g.mod_only && (
            <div className="absolute left-1.5 top-1.5 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-amber-400/90" title="官方深度Mod条目：本工具仅震动联动兜底">
              Mod条目
            </div>
          )}
        </div>
        <div className="p-3">
          <button className="w-full truncate text-left font-mono text-[10px] text-text-low hover:text-accent"
            title={(g.note || '') + '\n' + g.exe.join(' · ')}
            onClick={() => setDetail(g)}>
            {g.exe.length ? `${g.exe.slice(0, 3).join(' · ')}${g.exe.length > 3 ? ` +${g.exe.length - 3}` : ''}` : '（清单未录进程名 · 可手动定位）'}
          </button>
          {/* 扳机预设绑定：「走/不走」表达——未启用时是按钮，点了展开选择；启用后显示所选预设 */}
          <div className="mt-2 flex items-center gap-1.5">
            <Link2 size={11} className={`shrink-0 ${g.preset_id ? 'text-accent' : 'text-text-low'}`} />
            {g.preset_id || picking ? (
              <select
                value={g.preset_id}
                autoFocus={picking && !g.preset_id}
                onChange={(e) => link(g, e.target.value)}
                onBlur={() => setPicking(false)}   // picking 状态在父级（内联组件每 3s 随父重挂，state 放这必丢）
                title="切进本游戏自动套用该预设的扳机配置，切出自动解绑；选「不套用」= 关闭"
                className={`min-w-0 flex-1 rounded border bg-[#0d0d14] px-1.5 py-1 text-[11px] outline-none focus:border-accent-dim ${
                  g.preset_id ? 'border-accent/40 text-accent' : 'border-border-soft text-text-mid'}`}
              >
                <option value="">不套用扳机预设</option>
                {presets.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            ) : (
              <button
                className="min-w-0 flex-1 truncate rounded border border-border-soft bg-[#0d0d14] px-1.5 py-1 text-left text-[11px] text-text-low hover:text-text-mid"
                title="点这里为游戏选择扳机预设（进游戏自动套用，切出自动解绑）"
                onClick={() => setPicking(true)}
              >
                扳机预设：不走
              </button>
            )}
            <button className="btn !px-2 !py-1" disabled={!(g.preset_id || g.vib)} onClick={() => apply(g)} title="立即套用（震动联动 + 预设）">
              <Play size={11} />
            </button>
            <button className="btn !px-2 !py-1" onClick={() => pickExe(g)} title="特殊版本？选择游戏 exe 定位">
              <FolderOpen size={11} />
            </button>
            {!g.builtin && (
              <button className="btn btn-danger !px-2 !py-1" onClick={() => del(g)} title="删除">
                <Trash2 size={11} />
              </button>
            )}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <input ref={fileRef} type="file" accept=".exe" className="hidden" onChange={onExePicked} />

      {/* 工具条：搜索 + 筛选 + 自动切换 + 通用联动 + 官方导入 */}
      <div className="card flex flex-wrap items-center gap-3 px-4 py-3">
        <div className="flex min-w-56 flex-1 items-center gap-2 rounded-lg border border-border-soft bg-[#0d0d14] px-3 py-1.5">
          <Search size={14} className="shrink-0 text-text-low" />
          <input
            value={q} onChange={e => setQ(e.target.value)}
            placeholder="搜索游戏名 / 英文名 / 进程名…"
            className="w-full bg-transparent text-[13px] outline-none placeholder:text-text-low"
          />
        </div>
        <div className="flex gap-1">
          {([['all', '全部'], ['mine', '我的'], ['bound', '已绑定'], ['unbound', '未绑定'], ['vib', '震动联动']] as const).map(([v, l]) => (
            <button key={v} onClick={() => setFilter(v)}
              className={`rounded-md px-2.5 py-1 text-[12px] transition-colors ${
                filter === v ? 'bg-accent/15 text-accent' : 'text-text-mid hover:text-text-hi'
              }`}>{l}</button>
          ))}
        </div>
        <button className="btn !py-1 !text-[12px]" onClick={importOfficial} title="读本机飞智空间站的官方逐游戏适配库（震动联动参数 + 手感说明）">
          <Download size={12} /> 导入官方适配
        </button>
        <label className="flex cursor-pointer items-center gap-2 text-[12px] text-text-mid" title="任何游戏：游戏震动→扳机反馈，不震动→无反馈（设备端固件路由）">
          <input type="checkbox" checked={data.universal_vib}
            onChange={(e) => toggleUniversal(e.target.checked)}
            className="accent-[#22d3ee]" />
          通用震动联动
        </label>
        <label className="flex cursor-pointer items-center gap-2 text-[12px] text-text-mid">
          <input type="checkbox" checked={data.autoswitch}
            onChange={(e) => api.setAutoswitch(e.target.checked).catch(() => {})}
            className="accent-[#22d3ee]" />
          切到游戏自动套用
        </label>
      </div>

      <div className="flex items-center gap-3 text-[12px] text-text-mid">
        <span className="text-text-low">角标说明：<span className="text-accent">⚡官方适配</span>=官方震动调参，进游戏自动生效 ·
          <span className="text-violet-300">DS 原生</span>=原生 DualSense 扳机游戏（事件级效果需 ASB 桥）·
          卡片下方「扳机预设」=可选，绑定后进游戏自动套用</span>
      </div>

      <div className="flex items-center gap-3 text-[12px] text-text-mid">
        <span>前台：<span className="font-mono text-accent">{fg ?? '—'}</span></span>
        <span className="text-text-low">{filtered.length} / {pool.length} 款</span>
        {msg && <span className="ml-auto">{msg}</span>}
      </div>

      {/* 网格 */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
        {/* 添加卡置顶 */}
        <div className="card space-y-2 border-dashed p-3">
          <div className="flex items-center gap-1.5 text-[12px] text-text-mid"><Plus size={12} /> 添加游戏</div>
          <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
            placeholder="游戏名"
            className="w-full rounded border border-border-soft bg-[#0d0d14] px-2 py-1.5 text-[12px] outline-none focus:border-accent-dim" />
          <input value={form.exe} onChange={e => setForm({ ...form, exe: e.target.value })}
            placeholder="进程名 RDR2.exe（多个空格）"
            className="w-full rounded border border-border-soft bg-[#0d0d14] px-2 py-1.5 font-mono text-[11px] outline-none focus:border-accent-dim" />
          <select value={form.preset_id} onChange={e => setForm({ ...form, preset_id: e.target.value })}
            className="w-full rounded border border-border-soft bg-[#0d0d14] px-2 py-1.5 text-[11px] outline-none focus:border-accent-dim">
            <option value="">扳机预设（可选，进游戏自动套用）</option>
            {presets.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <button className="btn btn-primary w-full justify-center !py-1 text-[12px]" onClick={add}>
            <Plus size={11} /> 添加
          </button>
        </div>
        {filtered.slice(0, limit).map(g => (
          <Card key={g.id} g={g} picking={pickFor === g.id}
            setPicking={(v) => setPickFor(v ? g.id : null)} />
        ))}
      </div>

      {filtered.length > limit && (
        <div className="flex justify-center">
          <button className="btn" onClick={() => setLimit(l => l + PAGE)}>
            显示更多（还有 {filtered.length - limit} 款）
          </button>
        </div>
      )}
      {filtered.length === 0 && (
        <div className="card p-8 text-center text-[13px] text-text-low">
          没有匹配「{q}」的游戏——点上方「导入官方适配」拉入 70+ 款官方手工调参，或用添加卡自己录一个？
        </div>
      )}

      {/* 游戏详情浮层：官方手感说明 + 参数 */}
      {detail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm" onClick={() => setDetail(null)}>
          <div className="card max-h-[80vh] w-[520px] overflow-y-auto p-6" onClick={e => e.stopPropagation()}>
            <div className="mb-1 flex items-center gap-2">
              <Crosshair size={14} className="text-accent" />
              <span className="text-[15px] font-medium">{detail.name}</span>
              {detail.en && <span className="text-[12px] text-text-low">{detail.en}</span>}
            </div>
            <div className="mb-3 font-mono text-[11px] text-text-low">{detail.exe.join(' · ')}</div>
            {detail.vib && (
              <div className="mb-3 rounded-lg border border-accent/30 bg-accent/5 p-3">
                <div className="mb-1.5 flex items-center gap-1.5 text-[12px] text-accent"><Zap size={12} /> 官方震动联动参数（cmd 0x52）</div>
                <div className="grid grid-cols-3 gap-1 font-mono text-[11px] text-text-mid">
                  {Object.entries(detail.vib).map(([k, v]) => (
                    <div key={k}>{k}: <span className="text-accent">{v}</span></div>
                  ))}
                </div>
              </div>
            )}
            <div className="whitespace-pre-wrap text-[12px] leading-relaxed text-text-mid">
              {detail.note || '（无说明）'}
            </div>
            <div className="mt-4 flex gap-2">
              <button className="btn flex-1 justify-center" onClick={() => pickExe(detail)}>
                <FolderOpen size={12} /> 特殊版本？选择 exe
              </button>
              <button className="btn flex-1 justify-center" onClick={() => setDetail(null)}>关闭</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
