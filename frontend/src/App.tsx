import { useEffect, useRef, useState } from 'react'
import {
  BatteryCharging, BatteryFull, BatteryLow, BatteryMedium, FlaskConical,
  Gamepad2, LayoutDashboard, LibraryBig, Lightbulb, MonitorPlay, Orbit,
  Settings as SettingsIcon, SlidersHorizontal, TriangleAlert, Wand2, Zap,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { api, type EngineEvent } from './api'
import { useEngine } from './useEngine'
import { ErrorBoundary } from './ErrorBoundary'
import { DeviceGate } from './Offline'
import { StatusBanner } from './components/StatusBanner'
import { Toast } from './components/Toast'
import Overview from './pages/Overview'
import TriggerLab from './pages/TriggerLab'
import PresetLibrary from './pages/PresetLibrary'
import GameLibrary from './pages/GameLibrary'
import Macros from './pages/Macros'
import Lights from './pages/Lights'
import Screen from './pages/Screen'
import ExpLab from './pages/ExpLab'
import Motion from './pages/Motion'
import Settings from './pages/Settings'

type PageId = 'overview' | 'lab' | 'presets' | 'games' | 'macros' | 'lights' | 'screen' | 'motion' | 'explab' | 'settings'

// 分组与排序逻辑（动线：状态确认 → 玩 → 调 → 装扮 → 研究）：总览独占首位，
// 游戏库是最高频入口紧跟其后；调参→存档是一条动线所以实验室+预设配对。
const NAV: Array<{ id: PageId; label: string; icon: LucideIcon; group?: string }> = [
  { id: 'overview', label: '总览', icon: LayoutDashboard },
  { id: 'games', label: '游戏库', icon: LibraryBig, group: '游戏与适配' },
  { id: 'macros', label: '宏', icon: Wand2, group: '游戏与适配' },
  { id: 'lab', label: '扳机实验室', icon: SlidersHorizontal, group: '手感工坊' },
  { id: 'presets', label: '预设库', icon: Gamepad2, group: '手感工坊' },
  { id: 'lights', label: '灯光', icon: Lightbulb, group: '个性装备' },
  { id: 'screen', label: '屏幕', icon: MonitorPlay, group: '个性装备' },
  { id: 'motion', label: '体感', icon: Orbit, group: '个性装备' },
  { id: 'explab', label: '测试区', icon: FlaskConical, group: '进阶' },
  { id: 'settings', label: '设置', icon: SettingsIcon, group: '进阶' },
]

const PAGE_META: Record<PageId, { title: string; sub: string }> = {
  overview: { title: '总览', sub: '设备状态 · 实时反馈 · 事件流' },
  lab: { title: '扳机实验室', sub: '调参数、试手感，存成预设随时调用' },
  presets: { title: '预设库', sub: '打包好的手感配置，一键应用或绑定游戏' },
  games: { title: '游戏库', sub: '逐游戏适配 · 自动切换 · 官方 Mod 管理' },
  macros: { title: '宏', sub: '板载宏：写在手柄固件里，关软件也生效' },
  lights: { title: '灯光', sub: '灯效编辑与识别 · 写入设备驻留' },
  screen: { title: '屏幕', sub: '手柄屏幕动画推送（GIF → 抽帧 → 写入）' },
  motion: { title: '体感', sub: '陀螺瞄准 · 模拟器桥 · 试玩场' },
  explab: { title: '测试区', sub: '隐藏功能孵化区：真机验证后才转正' },
  settings: { title: '设置', sub: '联动行为 · 震动修复 · 数据与缓存' },
}

export default function App() {
  const [page, setPage] = useState<PageId>('overview')
  const { snap, connected, events } = useEngine()
  const [panicFlash, setPanicFlash] = useState(false)
  const [toast, setToast] = useState('')
  const lastAutoRef = useRef<EngineEvent | null>(null)
  const toastTimer = useRef(0)
  // 版本号：唯一真相源 = 仓库根 VERSION（后端 /api/version），禁止在界面硬编码
  const [appVer, setAppVer] = useState('')
  useEffect(() => {
    api.version()
      .then(v => setAppVer(v.sha ? `${v.version} (${v.sha})` : v.version))
      .catch(() => {})
  }, [])

  const proxy = snap?.proxy
  const taken = proxy?.holder === 'external'
  const online = snap?.device.online ?? false
  const mock = snap?.device.kind === 'mock'
  const batt = snap?.device.battery

  // 适配状态推导：gripBind/triggers 的 source 是工具行为的事实记录（game:名称 / preset:名称 / vib:universal）
  const gripSrc = snap?.state.gripBind.left?.source ?? snap?.state.gripBind.right?.source ?? ''
  const trigSrc = snap?.state.triggers.left?.source ?? snap?.state.triggers.right?.source ?? ''
  const gameAdapted = gripSrc.startsWith('game:') && !gripSrc.endsWith(':novib')
    ? gripSrc.slice('game:'.length)
    : null
  const universalVib = gripSrc.startsWith('vib:universal')
  const presetApplied = trigSrc.startsWith('preset:') ? trigSrc.slice('preset:'.length) : null
  const adapted = !!(gameAdapted || universalVib || presetApplied)

  // 自动切换 toast：只认 WS 实时推送（hist 标记的历史事件在重连/开窗时重放，不弹）。
  // ⚠ 定时器必须放 ref、不能当 effect cleanup：cleanup 在 effect 每次重跑（任意其他
  // WS 事件到达）时都会执行，若在这里清了 4s 定时器又提前 return 不重排 → 弹窗
  // 永不消失（2026-09-20 用户实测「离开游戏」提示赖着不走）。
  useEffect(() => {
    const latest = [...events].reverse().find(e => e.kind === 'autoswitch' && !e.hist)
    if (!latest || latest === lastAutoRef.current) return
    lastAutoRef.current = latest
    setToast(typeof latest.detail === 'string' ? latest.detail : '')
    if (toastTimer.current) clearTimeout(toastTimer.current)
    toastTimer.current = window.setTimeout(() => setToast(''), 4000)
  }, [events])

  const doPanic = async () => {
    setPanicFlash(true)
    try {
      await api.panic()
      setToast('已复位：马达归零，双扳机恢复出厂手感')
      setTimeout(() => setToast(''), 3000)
    } catch { /* 后端事件会同步状态 */ }
    setTimeout(() => setPanicFlash(false), 800)
  }

  return (
    <div className="flex h-full">
      {/* 侧栏：品牌区 + 分组导航 + 常驻状态区 */}
      <aside className="flex w-52 shrink-0 flex-col border-r border-border-soft/70 bg-[#0b0b11]/80">
        <div className="flex items-center gap-2.5 px-4 py-4">
          {/* 品牌瓦片：全 app 唯一的渐变描边（物以稀为贵） */}
          <div className="h-9 w-9 shrink-0 rounded-[10px] p-[1.5px]"
            style={{ background: 'linear-gradient(135deg,#22d3ee,#4c8dff)' }}>
            <div className="flex h-full w-full items-center justify-center rounded-[8.5px] bg-[#0b0b12]">
              <svg viewBox="0 0 64 64" className="h-7 w-7" aria-label="Apex5 Unleashed">
                <rect x="13" y="23" width="38" height="18" rx="9" fill="#22d3ee" />
                <ellipse cx="19" cy="37" rx="10" ry="11" fill="#22d3ee" />
                <ellipse cx="45" cy="37" rx="10" ry="11" fill="#22d3ee" />
                <rect x="19.5" y="27" width="5" height="12" rx="1.5" fill="#0a0a0f" />
                <rect x="16" y="30.5" width="12" height="5" rx="1.5" fill="#0a0a0f" />
                <circle cx="42.5" cy="28.5" r="2.2" fill="#0a0a0f" />
                <circle cx="46.5" cy="32.5" r="2.2" fill="#0a0a0f" />
                <circle cx="42.5" cy="36.5" r="2.2" fill="#0a0a0f" />
                <circle cx="38.5" cy="32.5" r="2.2" fill="#0a0a0f" />
                <circle cx="30.5" cy="28.6" r="1.4" fill="#0a0a0f" />
                <circle cx="33.5" cy="28.6" r="1.4" fill="#0a0a0f" />
              </svg>
            </div>
          </div>
          <div className="min-w-0">
            <div className="flex items-baseline gap-1.5">
              <span className="wordmark font-display text-[15px] font-bold leading-none tracking-wide">Apex5</span>
              <span className="text-[8px] font-semibold uppercase tracking-[.28em] text-text-low">Unleashed</span>
            </div>
            <div className="mt-1 truncate text-[10px] text-text-low">
              八爪鱼5 工具箱{appVer ? ` · v${appVer}` : ''}
            </div>
          </div>
        </div>

        <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 pb-2">
          {NAV.map(({ id, label, icon: Icon, group }, i) => (
            <div key={id}>
              {group && (i === 0 || NAV[i - 1].group !== group) && (
                <div className="px-3 pb-1 pt-3 text-[10px] font-medium uppercase tracking-[.22em] text-text-faint">
                  {group}
                </div>
              )}
              <button
                onClick={() => setPage(id)}
                className={`relative flex w-full items-center gap-2.5 rounded-[10px] px-3 py-2 text-[13px] transition-colors duration-150 ${
                  page === id
                    ? 'bg-accent/10 text-accent'
                    : 'text-text-mid hover:bg-white/4 hover:text-text-hi'
                }`}
              >
                {page === id && (
                  <span className="absolute left-0 top-1/2 h-4 w-[2px] -translate-y-1/2 rounded-full"
                    style={{ background: 'linear-gradient(180deg,#22d3ee,#4c8dff)' }} />
                )}
                <Icon size={17} className="shrink-0" />
                {label}
              </button>
            </div>
          ))}
        </nav>

        {/* 常驻状态区：任何页面都能回答"连着没、电量多少" */}
        <div className="space-y-2 px-3 pb-4">
          <div className="rounded-xl border border-border-soft/70 bg-card/60 px-3 py-2.5 text-[11px]">
            <div className={`flex items-center gap-1.5 ${online ? 'text-text-mid' : 'text-err'}`}>
              <span className={`status-dot ${online ? 'bg-ok' : 'bg-err'}`} />
              {online ? (mock ? '虚拟手柄（模拟）' : 'Apex 5 已连接') : '手柄未连接'}
            </div>
            {online && batt && (
              <div className={`mt-1.5 flex items-center gap-1.5 ${
                batt.charging ? 'text-accent' : batt.level <= 1 ? 'text-warn' : 'text-text-mid'}`}>
                {batt.charging ? <BatteryCharging size={11} />
                  : batt.level >= 4 ? <BatteryFull size={11} />
                  : batt.level >= 2 ? <BatteryMedium size={11} />
                  : <BatteryLow size={11} />}
                {batt.charging ? `充电中 · ${batt.level}/5` : `电量 ${batt.level}/5`}
              </div>
            )}
            {online && !adapted && (
              <div className="mt-1.5 flex items-center gap-1.5 text-text-low">
                <Zap size={11} /> 标准模式
              </div>
            )}
          </div>
          <button
            onClick={doPanic}
            className={`btn w-full justify-center !border-border-soft text-[12px] text-text-mid hover:text-err ${
              panicFlash ? 'anim-flash-err !border-err/60 text-err' : ''}`}
            title="手感的保险丝：效果卡死 / 马达乱震 / 扳机锁住时按一下——马达立刻归零、双扳机恢复出厂 Normal。平时正常玩用不着。"
          >
            <TriangleAlert size={13} /> {panicFlash ? '已复位 ✓' : '手柄复位'}
          </button>
        </div>
      </aside>

      {/* 主区 */}
      <main className="relative flex min-w-0 flex-1 flex-col">
        {/* 顶栏：页标题报头 + 状态胶囊群（连接/电量/适配/代理权常驻全页面） */}
        <header className="flex min-h-[52px] items-center justify-between gap-3 border-b border-border-soft/70 px-6 py-2">
          <div className="min-w-0">
            <div className="text-[15px] font-semibold leading-tight">{PAGE_META[page].title}</div>
            <div className="truncate text-[11px] text-text-low">{PAGE_META[page].sub}</div>
          </div>
          <div className="flex min-w-0 items-center justify-end gap-1.5 overflow-hidden">
            <span
              className={`tag ${connected ? 'border-ok/35 text-text-mid' : 'border-err/40 text-err'}`}
              title={connected
                ? '后台实时连接正常（127.0.0.1:18765）'
                : '无法连接软件后台（127.0.0.1:18765），正在自动重连'}>
              <span className={`status-dot ${connected ? 'bg-ok animate-dot' : 'bg-err'}`} />
              {connected ? '实时连接' : '重连中'}
            </span>
            {online && batt && (
              <span className={`tag ${batt.charging ? 'border-accent/40 text-accent' : 'text-text-mid'}`}
                title={batt.charging ? '充电中' : '电量'}>
                {batt.charging ? <BatteryCharging size={10} />
                  : batt.level >= 4 ? <BatteryFull size={10} />
                  : batt.level >= 2 ? <BatteryMedium size={10} />
                  : <BatteryLow size={10} />}
                {batt.level}/5
              </span>
            )}
            {online && adapted && (
              <span className="tag min-w-0 max-w-[240px] border-accent/40 text-accent" title="自动切换已应用的适配">
                <Zap size={10} className="shrink-0" />
                <span className="truncate">
                  {gameAdapted ? `适配中：${gameAdapted}`
                    : universalVib ? '通用震动联动' : ''}
                  {presetApplied ? ` · 预设 ${presetApplied}` : ''}
                </span>
              </span>
            )}
            {taken && (
              proxy?.mild ? (
                /* ADR-023：飞智空间站 init 指纹命中 → 中性提示，不弹「被接管」警告 */
                <span className="tag text-text-mid">飞智空间站初始化中，稍后自动收回</span>
              ) : (
                <span className="tag min-w-0 max-w-[300px] border-warn/40 text-warn" title={`被 ${proxy?.detail || '外部进程'} 接管，15s 无活动自动收回`}>
                  <span className="truncate">被接管：{proxy?.detail || '未知进程'}</span>
                  <button className="shrink-0 rounded px-1 text-warn hover:bg-warn/15"
                    onClick={() => api.reclaim().catch(() => {})}>
                    夺回
                  </button>
                </span>
              )
            )}
          </div>
        </header>

        {/* 全局离线横幅（展示件在 components/StatusBanner.tsx） */}
        <StatusBanner connected={connected} online={online} mock={mock} />

        {/* 自动切换 toast：进入/离开游戏时全页面可见的工具行为提示（展示件在 components/Toast.tsx） */}
        {toast && <Toast msg={toast} />}

        <div className="min-h-0 flex-1 overflow-y-auto p-6">
          <div key={page} className="anim-page mx-auto w-full max-w-[1120px]">
            <ErrorBoundary page={page}>
              {page === 'overview' && <Overview snap={snap} events={events} onPanic={doPanic} />}
              {page === 'lab' && <TriggerLab snap={snap} />}
              {page === 'presets' && <PresetLibrary snap={snap} />}
              {page === 'games' && <GameLibrary />}
              {page === 'macros' && <Macros events={events} online={online} />}
              {page === 'lights' && <DeviceGate online={online}><Lights /></DeviceGate>}
              {page === 'screen' && <DeviceGate online={online}><Screen events={events} /></DeviceGate>}
              {page === 'motion' && <Motion />}
              {page === 'explab' && <ExpLab />}
              {page === 'settings' && <Settings />}
            </ErrorBoundary>
          </div>
        </div>
      </main>
    </div>
  )
}
