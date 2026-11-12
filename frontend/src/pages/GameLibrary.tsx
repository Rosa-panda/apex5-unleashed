// 游戏库：一游戏一卡（2026-11 重整）。每张卡 = 来源（官方空间站 / DS推算 / 自定义）
// + 震动联动参数 + 可选官方 Mod；卡上直接写明「进游戏会用哪个方案」。
// 支持导入/导出自定义配置、手动指定空间站官方库位置、禁用某款游戏的适配。
// 按几百款规模设计 —— 搜索(名称/英文名/进程名) + 筛选 + 封面卡 + 分段渲染
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Ban, Crosshair, Download, FolderOpen, Info, MonitorPlay, Play, Plus, Power, Search, Share2, Trash2, Upload, Zap } from 'lucide-react'
import { api } from '../api'
import { usePolling } from '../hooks/usePolling'

interface VibParams { filter: number; scale: number; stroke: number; press: number; strength: number; freq: number }

interface ModInfo {
  url?: string; name?: string; version?: string; start_type?: number; process?: string
}

interface GameProfile {
  id: string
  name: string
  en?: string
  exe: string[]
  note: string
  image?: string
  builtin: boolean
  vib?: VibParams | null
  mod?: ModInfo
  origin: 'official' | 'ds' | 'custom'            // 卡片来源（角标）
  vib_origin?: 'official' | 'guess' | 'custom' | null   // 震动参数来源
  user_id?: string | null                         // 这张卡上你自己的配置（可删除恢复默认）
}

interface ModsStatus {
  mods: Array<{ gid: string; installed: boolean; enabled: boolean; installing: boolean; running: boolean }>
  active_gid: string | null
  ingress: { port: number | null; error: string; packets: number; applied: number } | null
}

interface GamesResp {
  builtin: GameProfile[]
  user: GameProfile[]
  foreground: string | null
  autoswitch: boolean
  universal_vib: boolean
  disabled?: string[]
  active?: { gid: string | null; source: string; origin: string } | null
}

type ModStat = ModsStatus['mods'][number] | undefined

const PAGE = 24

const ORIGIN_BADGE: Record<GameProfile['origin'], { label: string; cls: string; tip: string }> = {
  official: { label: '官方空间站', cls: 'text-accent', tip: '飞智空间站官方适配清单里的游戏' },
  ds: { label: 'DS推算', cls: 'text-violet-300', tip: '原生支持 DualSense 的游戏：官方没有参数，按游戏题材从官方调参推算' },
  custom: { label: '自定义', cls: 'text-sky-300', tip: '你自己添加或导入的配置' },
}

const VIB_ORIGIN: Record<string, string> = { official: '官方调参', guess: '推算参数', custom: '自定义参数' }

// 生效来源 → 展示文案
const SOURCE_LABEL: Record<string, string> = { mod: 'Mod', vib: '震动联动', universal: '通用震动联动' }

// 卡上的「方案」一句话：进这个游戏到底会用什么（issue #2 的核心诉求）
function planOf(g: GameProfile, ms: ModStat, disabled: boolean): { text: string; cls: string } {
  if (disabled) return { text: '已禁用：进游戏不做任何适配', cls: 'text-text-low' }
  const vib = g.vib ? `震动联动·${VIB_ORIGIN[g.vib_origin ?? ''] ?? '参数'}` : ''
  const pluginMod = !!g.mod && (g.mod.start_type ?? 1) !== 1
  if (g.mod && !pluginMod && ms?.enabled && ms?.installed)
    return { text: `Mod 事件级${vib ? `（Mod 没在跑时用${vib}）` : ''}`, cls: 'text-accent' }
  if (vib) return { text: vib + (g.mod && !pluginMod ? '；装好并启用 Mod 后改用 Mod' : ''), cls: 'text-text-mid' }
  if (g.mod && !pluginMod) return { text: '只有 Mod：安装并启用后生效', cls: 'text-amber-300' }
  if (pluginMod) return { text: '官方 Mod 为游戏目录插件型，暂不支持', cls: 'text-text-low' }
  return { text: '无适配参数', cls: 'text-text-low' }
}

// 封面图：走后端本地缓存代理（外链 CDN 直连不稳，见 gameimg.py）。
// 404 = 后端还在下 → 指数退避重试（3s 起步封顶 30s）；骨架占位 + 加载完淡入，
// 批量渲染不闪不卡。浏览器对 no-store 404 不缓存，重试必达。
function GameImg({ gid }: { gid: string }) {
  const [attempt, setAttempt] = useState(0)
  const [ready, setReady] = useState(false)
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current) }, [])
  return (
    <div className="relative h-full w-full bg-[#10101a]">
      {!ready && <div className="absolute inset-0 animate-pulse bg-white/4" />}
      <img
        src={`/api/game-img/${gid}?r=${attempt}`}
        alt="" loading="lazy"
        onLoad={() => setReady(true)}
        onError={() => {
          if (attempt >= 10) return
          timer.current = window.setTimeout(
            () => setAttempt(a => a + 1), Math.min(3000 * 2 ** attempt, 30000))
        }}
        className={`h-full w-full object-cover transition-opacity duration-300 ${
          ready ? 'opacity-70 group-hover:opacity-100' : 'opacity-0'}`}
      />
    </div>
  )
}

type ModAction = 'install' | 'uninstall' | 'enable' | 'disable' | 'stop' | 'open'

// 游戏卡：模块级组件（内联定义会让 3s 轮询每次整棵卸载重挂，封面重载、焦点丢失）
function GameCard({ g, fg, ms, effective, disabled,
                    onApply, onDel, onPickExe, onModAction, onDetail, onToggleDisabled, onExport }: {
  g: GameProfile
  fg: string | null
  ms: ModStat
  effective: string | null   // 本卡正在生效时的来源（mod/vib/...），未生效 null
  disabled: boolean
  onApply: (g: GameProfile) => void
  onDel: (g: GameProfile) => void
  onPickExe: (g: GameProfile) => void
  onModAction: (g: GameProfile, what: ModAction) => void
  onDetail: (g: GameProfile) => void
  onToggleDisabled: (g: GameProfile) => void
  onExport: (g: GameProfile) => void
}) {
  const active = !!fg && g.exe.some(e => e.replace(/\.exe$/i, '') === fg.replace(/\.exe$/i, ''))
  const pluginType = !!g.mod && (g.mod.start_type ?? 1) !== 1
  const badge = ORIGIN_BADGE[g.origin] ?? ORIGIN_BADGE.custom
  const plan = planOf(g, ms, disabled)
  return (
      <div className={`card overflow-hidden p-0 ${active ? 'card-selected' : 'card-hover'} ${disabled ? 'opacity-50' : ''}`}>
        {/* 封面条 */}
        <div className="relative h-20 w-full overflow-hidden bg-inset">
          {g.image
            ? <GameImg gid={g.id} />
            : <div className="flex h-full items-center justify-center text-text-low"><MonitorPlay size={18} /></div>}
          <div className="absolute inset-x-0 bottom-0 flex items-center gap-1.5 bg-gradient-to-t from-black/80 to-transparent px-3 pb-1 pt-4">
            <span className="truncate text-[13px] font-medium">{g.name}</span>
            {disabled
              ? <span className="tag shrink-0 !text-text-low">已禁用</span>
              : effective
                ? <span className="tag shrink-0 border-accent/50 !text-accent" title="当前真正生效的适配">生效中·{SOURCE_LABEL[effective] ?? effective}</span>
                : active && <span className="tag shrink-0 text-text-low" title="正在玩，但没有适配在生效（无参数，或自动套用已关闭）">正在玩·未生效</span>}
          </div>
          <div className={`absolute right-1.5 top-1.5 rounded bg-black/60 px-1.5 py-0.5 text-[10px] ${badge.cls}`} title={badge.tip}>
            {badge.label}
          </div>
          {g.mod && !pluginType && (
            <div className={`absolute left-1.5 top-1.5 flex items-center gap-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] ${
              ms?.running ? 'text-accent' : ms?.enabled ? 'text-amber-300' : 'text-amber-400/70'}`}
              title="有官方事件级 Mod：安装并启用后，进游戏自动拉起，扳机按游戏事件实时反馈">
              <Zap size={9} /> {ms?.running ? 'Mod 运行中' : ms?.enabled ? 'Mod·已启用' : 'Mod 可用'}
            </div>
          )}
        </div>
        <div className="p-3">
          <button className="w-full truncate text-left font-mono text-[10px] text-text-low hover:text-accent"
            title={(g.note || '') + '\n' + g.exe.join(' · ')}
            onClick={() => onDetail(g)}>
            {g.exe.slice(0, 3).join(' · ')}{g.exe.length > 3 ? ` +${g.exe.length - 3}` : ''}
          </button>
          {/* 方案：进游戏会用什么——一句话说清 */}
          <div className={`mt-1.5 truncate text-[11px] ${plan.cls}`} title={plan.text}>方案：{plan.text}</div>
          <div className="mt-2 flex items-center gap-1.5">
            <button className="btn !px-2 !py-1" disabled={!g.vib || disabled} onClick={() => onApply(g)} title="立即套用震动联动参数">
              <Play size={11} />
            </button>
            <button className="btn !px-2 !py-1" onClick={() => onPickExe(g)} title="特殊版本？选择游戏 exe，追加进程名">
              <FolderOpen size={11} />
            </button>
            <button className="btn !px-2 !py-1" onClick={() => onExport(g)} title="导出这款游戏的配置（可修改后再导入，或分享给别人）">
              <Share2 size={11} />
            </button>
            <button className={`btn !px-2 !py-1 ${disabled ? 'btn-primary' : ''}`} onClick={() => onToggleDisabled(g)}
              title={disabled ? '恢复这款游戏的适配' : '禁用这款游戏的适配（震动联动和 Mod 都不再生效）'}>
              {disabled ? <Power size={11} /> : <Ban size={11} />}
            </button>
            {g.user_id && (
              <button className="btn btn-danger !px-2 !py-1" onClick={() => onDel(g)}
                title={g.origin === 'custom' ? '删除这个自定义游戏' : '删除你的自定义配置，恢复默认参数'}>
                <Trash2 size={11} />
              </button>
            )}
          </div>
          {/* Mod 行：安装 → 启用 → 进游戏自动拉起；文件夹里可改 Mod 自己的配置、或放入自制 Mod */}
          {g.mod && !pluginType && (
            <div className="mt-1.5 flex items-center gap-1.5 text-[11px]">
              <span className={`shrink-0 ${ms?.running ? 'text-accent' : ms?.enabled ? 'text-amber-300' : 'text-text-low'}`}>
                {ms?.running ? '⚡运行中' : ms?.installing ? '⇣下载中…' : ms?.enabled ? '已启用' : ms?.installed ? '已装' : '未装'}
              </span>
              {!ms?.installed && !ms?.installing && g.mod.url && (
                <button className="btn !flex-1 !justify-center !py-0.5 !text-[10px]" onClick={() => onModAction(g, 'install')}
                  title={`从飞智官方 CDN 下载 Mod（${g.mod.version ?? ''}），本机安装`}>
                  <Download size={9} /> 安装 Mod
                </button>
              )}
              {!ms?.installed && !ms?.installing && !g.mod.url && (
                <span className="flex-1 truncate text-text-low" title={`把 ${g.mod.name} 放进 Mod 文件夹后即可启用`}>放入 {g.mod.name} 后启用</span>
              )}
              {ms?.installed && (
                <button className={`btn !flex-1 !justify-center !py-0.5 !text-[10px] ${ms.enabled ? 'btn-danger' : 'btn-primary'}`}
                  onClick={() => onModAction(g, ms.enabled ? 'disable' : 'enable')}
                  title={ms.enabled ? '停用：不再自动拉起（运行中会立即停止），回到震动联动' : '启用后进游戏自动拉起 Mod，Mod 运行期间震动联动让位'}>
                  {ms.enabled ? '停用 Mod' : '启用 Mod'}
                </button>
              )}
              {ms?.running && (
                <button className="btn !py-0.5 !text-[10px]" onClick={() => onModAction(g, 'stop')} title="立即停止当前 Mod">
                  ■
                </button>
              )}
              <button className="btn !py-0.5 !text-[10px]" onClick={() => onModAction(g, 'open')}
                title="打开这款游戏的 Mod 文件夹：修改 Mod 自带的配置文件，或放入自制/手动下载的 Mod">
                <FolderOpen size={9} />
              </button>
            </div>
          )}
        </div>
      </div>
  )
}

export default function GameLibrary() {
  const [data, setData] = useState<GamesResp>({ builtin: [], user: [], foreground: null, autoswitch: true, universal_vib: false })
  const [q, setQ] = useState('')
  const [filter, setFilter] = useState<'all' | 'official' | 'ds' | 'custom' | 'mod'>('all')
  const [limit, setLimit] = useState(PAGE)
  const [msg, setMsg] = useState('')
  const [form, setForm] = useState({ name: '', exe: '' })
  const [detail, setDetail] = useState<GameProfile | null>(null)
  const [mods, setMods] = useState<ModsStatus>({ mods: [], active_gid: null, ingress: null })
  const [addOpen, setAddOpen] = useState(false)
  const [src, setSrc] = useState<{ available: boolean; path: string; custom: string } | null>(null)
  const fileRef = useRef<HTMLInputElement | null>(null)
  const cfgRef = useRef<HTMLInputElement | null>(null)
  const exeTarget = useRef<string | null>(null)

  const load = useCallback(() => {
    api.games().then(setData).catch(() => {})
    api.mods().then(setMods).catch(() => {})
  }, [])
  usePolling(load, 3000, [load])

  // 官方库位置：不进 3s 轮询（自动识别要扫注册表），进页面 + 改位置后各查一次
  const loadSrc = useCallback(() => { api.officialSrc().then(setSrc).catch(() => {}) }, [])
  useEffect(loadSrc, [loadSrc])

  const pickSrc = async () => {
    try {
      const r = await api.pickOfficialSrc()
      if (r.cancelled) return
      setMsg(`✓ 官方库位置已设为 ${r.path}`)
    } catch (e) { setMsg(`✗ ${(e as Error).message}`) }
    loadSrc()
  }

  const resetSrc = async () => {
    try {
      await api.setOfficialSrc('')
      setMsg('✓ 已恢复自动识别官方库位置')
    } catch (e) { setMsg(`✗ ${(e as Error).message}`) }
    loadSrc()
  }

  const fg = data.foreground
  const disabledSet = useMemo(() => new Set(data.disabled ?? []), [data])
  const modOf = (gid: string) => mods.mods.find(m => m.gid === gid)

  const pool = useMemo(() => [...data.user, ...data.builtin], [data])
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return pool.filter(g => {
      if (filter === 'official' && g.origin !== 'official') return false
      if (filter === 'ds' && g.origin !== 'ds') return false
      if (filter === 'custom' && !(g.origin === 'custom' || g.user_id)) return false
      if (filter === 'mod' && !g.mod) return false
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
      await api.applyGame(g.id)
      setMsg(`✓ 已套用「${g.name}」震动联动`)
    } catch (e) { setMsg(`✗ ${(e as Error).message}`) }
  }

  const toggleDisabled = async (g: GameProfile) => {
    const off = !disabledSet.has(g.id)
    try {
      await api.setGameDisabled(g.id, off)
      setMsg(off ? `✓ 已禁用「${g.name}」的适配` : `✓ 已恢复「${g.name}」`)
    } catch (e) { setMsg(`✗ ${(e as Error).message}`) }
    load()
  }

  const del = async (g: GameProfile) => {
    if (!g.user_id) return
    try {
      await api.deleteGame(g.user_id)
      setMsg(g.origin === 'custom' ? `✓ 已删除「${g.name}」` : `✓ 「${g.name}」已恢复默认参数`)
    } catch (e) { setMsg(`✗ ${(e as Error).message}`) }
    load()
  }

  const exportGame = async (g: GameProfile) => {
    try {
      const r = await api.exportGame(g.id)
      if (r.cancelled) return
      setMsg(`✓ 已导出到 ${r.path}`)
    } catch (e) { setMsg(`✗ ${(e as Error).message}`) }
  }

  const add = async () => {
    if (!form.name.trim() || !form.exe.trim()) return
    try {
      await api.saveGame({ name: form.name.trim(), exe: form.exe.split(/[,，\s]+/), note: '' })
      setForm({ name: '', exe: '' })
      setAddOpen(false)
      setMsg('✓ 已添加（通用参数起步，可导出修改后再导入）')
    } catch (e) { setMsg(`✗ ${(e as Error).message}`) }
    load()
  }

  const importOfficial = async () => {
    try {
      const r = await api.importOfficial() as { result: { imported: number; updated: number; skipped: number } }
      setMsg(`✓ 官方适配：新增 ${r.result.imported} 款、更新 ${r.result.updated} 款（无震动参数的 ${r.result.skipped} 条跳过）`)
    } catch (e) { setMsg(`✗ ${(e as Error).message}`) }
    load()
  }

  // 导入自定义配置：读本地 JSON（单个对象或数组）→ 后端校验落盘
  const onCfgPicked = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (!f) return
    try {
      const parsed = JSON.parse(await f.text())
      const r = await api.importConfig(parsed)
      setMsg(`✓ 已导入 ${r.count} 款：${r.names.join('、')}`)
    } catch (err) {
      setMsg(`✗ 导入失败：${err instanceof SyntaxError ? '不是有效的 JSON 文件' : (err as Error).message}`)
    }
    load()
  }

  const toggleUniversal = async (on: boolean) => {
    setData(d => ({ ...d, universal_vib: on }))
    try { await api.setUniversalVib(on) } catch (e) { setMsg(`✗ ${(e as Error).message}`) }
  }

  // Mod 管家：安装/启停/停止/打开文件夹 → 刷新
  const modAction = async (g: GameProfile, what: ModAction) => {
    try {
      if (what === 'install') {
        setMsg(`⇣ 正在下载「${g.name}」官方 Mod…`)
        await api.modInstall(g.id)
        setMsg(`✓ 「${g.name}」Mod 安装完成`)
      } else if (what === 'uninstall') await api.modUninstall(g.id)
      else if (what === 'enable') {
        await api.modEnable(g.id, true)
        setMsg(`✓ 「${g.name}」Mod 已启用——进游戏自动拉起，运行期间震动联动让位`)
      } else if (what === 'disable') await api.modEnable(g.id, false)
      else if (what === 'open') await api.modOpenDir(g.id)
      else await api.modStop()
    } catch (e) { setMsg(`✗ ${(e as Error).message}`) }
    load()
  }

  // 自定义 exe：选文件 → 追加进程名（特殊版本游戏定位）
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
      setMsg(`✓ 已追加进程名 ${f.name}`)
    } catch (err) { setMsg(`✗ ${(err as Error).message}`) }
    load()
  }

  const activeGame = data.active?.gid ? pool.find(g => g.id === data.active?.gid) : undefined

  return (
    <div className="space-y-4">
      <input ref={fileRef} type="file" accept=".exe" className="hidden" onChange={onExePicked} />
      <input ref={cfgRef} type="file" accept=".json,application/json" className="hidden" onChange={onCfgPicked} />

      {/* 工具条：搜索 + 筛选 + 导入 + 开关（sticky：滚动几百款时搜索常驻） */}
      <div className="card sticky top-0 z-10 flex flex-wrap items-center gap-3 bg-[#0d0d15f5] px-4 py-3 backdrop-blur">
        <div className="flex min-w-56 flex-1 items-center gap-2 rounded-lg border border-border-soft bg-[#0d0d14] px-3 py-1.5">
          <Search size={14} className="shrink-0 text-text-low" />
          <input
            value={q} onChange={e => setQ(e.target.value)}
            placeholder="搜索游戏名 / 英文名 / 进程名…"
            className="w-full bg-transparent text-[13px] outline-none placeholder:text-text-low"
          />
        </div>
        <div className="flex gap-1">
          {([['all', '全部'], ['official', '官方空间站'], ['ds', 'DS推算'], ['custom', '自定义'], ['mod', '有 Mod']] as const).map(([v, l]) => (
            <button key={v} onClick={() => setFilter(v)}
              className={`rounded-md px-2.5 py-1 text-[12px] transition-colors ${
                filter === v ? 'bg-accent/15 text-accent' : 'text-text-mid hover:text-text-hi'
              }`}>{l}</button>
          ))}
        </div>
        <button className="btn !py-1 !text-[12px]" onClick={() => cfgRef.current?.click()}
          title="导入别人分享或你自己写的游戏配置（.json，格式见 README「自定义适配」）">
          <Upload size={12} /> 导入配置
        </button>
        <button className="btn !py-1 !text-[12px]" onClick={importOfficial} title="从本机飞智空间站同步官方适配（新版空间站新增的游戏、更新过的参数）">
          <Download size={12} /> 同步空间站
        </button>
        <span className={`flex max-w-72 items-center gap-1.5 text-[11px] ${src?.available ? 'text-text-low' : 'text-amber-300'}`}
          title={src?.available ? src.path : '没找到飞智空间站官方库：解压版/绿色版请手动选择空间站目录'}>
          <span className="truncate">
            {src ? (src.available ? `${src.custom ? '手动' : '自动'}：${src.path}` : '未找到官方库') : '…'}
          </span>
          <button className="shrink-0 text-accent hover:underline" onClick={pickSrc}
            title="选择飞智空间站目录（或直接装着 adapterTriggerGames.json 的目录）">库位置</button>
          {src?.custom && (
            <button className="shrink-0 hover:text-text-mid hover:underline" onClick={resetSrc}>恢复自动</button>
          )}
        </span>
        <label className="flex cursor-pointer items-center gap-2 text-[12px] text-text-mid" title="库里没有的游戏：游戏震动→扳机反馈，不震动→无反馈（设备端固件路由）">
          <span className="switch">
            <input type="checkbox" checked={data.universal_vib}
              onChange={(e) => toggleUniversal(e.target.checked)} />
            <span className="switch-track" />
          </span>
          通用震动联动
        </label>
        <label className="flex cursor-pointer items-center gap-2 text-[12px] text-text-mid">
          <span className="switch">
            <input type="checkbox" checked={data.autoswitch}
              onChange={(e) => api.setAutoswitch(e.target.checked).catch(() => {})} />
            <span className="switch-track" />
          </span>
          切到游戏自动套用
        </label>
      </div>

      <div className="flex items-center gap-3 text-[12px] text-text-mid">
        <span
          className="tag cursor-help text-text-low"
          title={'每款游戏一张卡。右上角 = 来源：官方空间站（飞智官方清单）/ DS推算（原生 DualSense 游戏，参数按题材推算）/ 自定义（你添加或导入的）。\n'
            + '左上角「Mod」= 这款游戏有官方事件级 Mod：安装并启用后进游戏自动拉起，Mod 运行期间震动联动让位。\n'
            + '卡上「方案」一行写明进游戏实际会用什么；顶部「生效」显示此刻正在生效的适配。'}
        >
          <Info size={11} /> 说明
        </span>
        <span className="text-text-low">{filtered.length} / {pool.length} 款</span>
        {fg && <span>前台：<span className="font-mono text-accent">{fg}</span></span>}
        {fg && (
          <span title="此刻真正生效的适配">
            生效：<span className="text-accent">{data.active
              ? `${activeGame ? `${activeGame.name} · ` : ''}${SOURCE_LABEL[data.active.source] ?? data.active.source}${
                data.active.origin ? `（${VIB_ORIGIN[data.active.origin] ?? data.active.origin}）` : ''}`
              : '无'}</span>
          </span>
        )}
        {msg && <span className="ml-auto">{msg}</span>}
        {mods.ingress?.port && (
          <span className={`shrink-0 text-text-low ${msg ? '' : 'ml-auto'}`} title="DSX 事件流入口（官方 Mod 走这里）">
            DSX :{mods.ingress.port} · 收 {mods.ingress.packets} / 出 {mods.ingress.applied}
          </span>
        )}
      </div>

      {/* 网格 */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
        {/* 添加卡置顶（默认收起，点击展开表单） */}
        {!addOpen ? (
          <button className="card card-hover flex min-h-44 flex-col items-center justify-center gap-1.5 border-dashed p-3 text-text-low hover:text-text-mid"
            onClick={() => setAddOpen(true)}>
            <Plus size={18} />
            <span className="text-[12px]">添加游戏</span>
          </button>
        ) : (
          <div className="card space-y-2 border-dashed p-3">
            <div className="flex items-center justify-between text-[12px] text-text-mid">
              <span className="flex items-center gap-1.5"><Plus size={12} /> 添加游戏</span>
              <button className="text-[11px] text-text-low hover:text-text-mid" onClick={() => setAddOpen(false)}>收起</button>
            </div>
            <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
              placeholder="游戏名"
              className="input w-full !text-[12px]" />
            <input value={form.exe} onChange={e => setForm({ ...form, exe: e.target.value })}
              placeholder="进程名 RDR2.exe（多个空格）"
              className="input w-full font-mono !text-[11px]" />
            <div className="text-[10px] leading-relaxed text-text-low">
              以通用震动参数起步；想精调就点卡上的导出，改好参数后「导入配置」。
            </div>
            <button className="btn btn-primary w-full justify-center !py-1 text-[12px]" onClick={add}>
              <Plus size={11} /> 添加
            </button>
          </div>
        )}
        {filtered.slice(0, limit).map(g => (
          <GameCard key={g.id} g={g} fg={fg} ms={modOf(g.id)}
            effective={data.active?.gid === g.id ? data.active.source : null}
            disabled={disabledSet.has(g.id)}
            onApply={apply} onDel={del} onToggleDisabled={toggleDisabled} onExport={exportGame}
            onPickExe={pickExe} onModAction={modAction} onDetail={setDetail} />
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
          没有匹配「{q}」的游戏——可以用添加卡自己录一个，或「导入配置」导入别人写好的方案。
        </div>
      )}

      {/* 游戏详情抽屉：右侧滑入（来源 + 方案 + 参数 + 说明） */}
      {detail && (
        <div className="fixed inset-0 z-50 bg-black/60" onClick={() => setDetail(null)}>
          <div className="anim-page absolute right-0 top-0 h-full w-[420px] overflow-y-auto border-l border-border-soft bg-card p-6 shadow-2xl"
            onClick={e => e.stopPropagation()}>
            <div className="mb-1 flex items-center gap-2">
              <Crosshair size={14} className="text-accent" />
              <span className="text-[15px] font-medium">{detail.name}</span>
              {detail.en && <span className="text-[12px] text-text-low">{detail.en}</span>}
            </div>
            <div className="mb-1 text-[11px] text-text-low">
              来源：<span className={ORIGIN_BADGE[detail.origin]?.cls}>{ORIGIN_BADGE[detail.origin]?.label}</span>
            </div>
            <div className="mb-3 font-mono text-[11px] text-text-low">{detail.exe.join(' · ')}</div>
            <div className="mb-3 text-[12px] text-text-mid">
              方案：{planOf(detail, modOf(detail.id), disabledSet.has(detail.id)).text}
            </div>
            {detail.vib && (
              <div className="mb-3 rounded-xl border border-accent/30 bg-accent/5 p-3">
                <div className="mb-1.5 flex items-center gap-1.5 text-[12px] text-accent">
                  <Zap size={12} /> 震动联动参数 · {VIB_ORIGIN[detail.vib_origin ?? ''] ?? ''}
                </div>
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
                <FolderOpen size={12} /> 选择 exe
              </button>
              <button className="btn flex-1 justify-center" onClick={() => exportGame(detail)}>
                <Share2 size={12} /> 导出配置
              </button>
              <button className="btn flex-1 justify-center" onClick={() => setDetail(null)}>关闭</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
