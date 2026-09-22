// 总览驾驶舱（2026-09-20 重构）：设备仪表 + 适配英雄区 + 扳机/震动实时可视化 +
// 电量走势 + 会话统计 + 快速操作 + 事件时间线。数据全部来自现有 snap/events/REST。
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, Bluetooth, Crosshair, Eraser, Gauge, Monitor,
  ScrollText, Usb, Waves, Zap,
} from 'lucide-react'
import { api, type EngineEvent, type EngineSnapshot, type TriggerState } from '../api'
import PadLiveCard from './PadTest'

const MODE_LABEL: Record<string, string> = {
  normal: 'Normal', race: 'Race 赛车', sniper: 'Sniper 狙击',
  recoil: 'Recoil 后坐力', lock: 'Lock 锁定', vibration: 'Vibration 振动',
}
const PARAM_LABEL: Record<string, string> = {
  stroke: '行程', resistance: '阻尼', press: '触发点', strength: '力度',
  freq: '频率', recoil_stroke: '回弹', match: '同步',
}

const C = { accent: '#22d3ee', ok: '#34d399', warn: '#fbbf24', err: '#f87171' }

function battColor(level: number, charging: boolean) {
  return charging ? C.accent : level >= 4 ? C.ok : level >= 2 ? C.warn : C.err
}

// 电量环：level 0..5 → 环形进度
function BatteryRing({ level, charging }: { level: number; charging: boolean }) {
  const pct = Math.max(0, Math.min(1, level / 5))
  const r = 26, cir = 2 * Math.PI * r
  return (
    <svg width="76" height="76" viewBox="0 0 76 76" className="shrink-0">
      <circle cx="38" cy="38" r={r} fill="none" stroke="#1c1c28" strokeWidth="7" />
      <circle cx="38" cy="38" r={r} fill="none" stroke={battColor(level, charging)} strokeWidth="7"
        strokeDasharray={cir} strokeDashoffset={cir * (1 - pct)} strokeLinecap="round"
        transform="rotate(-90 38 38)" style={{ transition: 'stroke-dashoffset .8s, stroke .4s' }} />
      <text x="38" y="37" textAnchor="middle" fill="#e5e7eb" fontSize="15" fontWeight="600">{level}</text>
      <text x="38" y="49" textAnchor="middle" fill="#6b7280" fontSize="8">/ 5 格</text>
    </svg>
  )
}

// 电量走势迷你线（最近读数）
function Spark({ data }: { data: number[] }) {
  if (data.length < 2) return <div className="h-7 text-[11px] text-text-low">采集中…</div>
  const w = 130, h = 28
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - (v / 5) * (h - 3) - 1}`).join(' ')
  return (
    <svg width={w} height={h} className="overflow-visible">
      <polyline points={pts} fill="none" stroke={C.accent} strokeWidth="1.5" strokeLinejoin="round" />
      <circle cx={w} cy={h - (data[data.length - 1] / 5) * (h - 3) - 1} r="2.5" fill={C.accent} />
    </svg>
  )
}

// 适配状态推导（与 App.tsx 同源：账本 source 前缀是工具行为的事实记录）
function deriveAdapt(snap: EngineSnapshot | null) {
  const grip = snap?.state.gripBind.left?.source ?? snap?.state.gripBind.right?.source ?? ''
  const trig = snap?.state.triggers.left?.source ?? snap?.state.triggers.right?.source ?? ''
  const game = grip.startsWith('game:') && !grip.endsWith(':novib') ? grip.slice(5) : null
  const uni = grip.startsWith('vib:universal')
  const preset = trig.startsWith('preset:') ? trig.slice(7) : null
  return { game, uni, preset, active: !!(game || uni || preset) }
}

// 单侧扳机可视化：模式 + 参数条（值/255 归一）
function TriggerRow({ t, side }: { t: TriggerState | null; side: 'left' | 'right' }) {
  const params = Object.entries(t?.params ?? {}).filter(([k]) => k !== 'match')
  const sync = t?.params?.match
  return (
    <div className="rounded-lg border border-border-soft bg-[#0d0d14] p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-mono text-[12px] text-text-mid">{side === 'left' ? 'LT 左扳机' : 'RT 右扳机'}</span>
        {t ? (
          <span className="tag border-accent/40 text-accent">{MODE_LABEL[t.mode] ?? t.mode}</span>
        ) : <span className="tag">normal · 出厂手感</span>}
      </div>
      {t ? (
        <div className="space-y-1.5">
          {params.map(([k, v]) => (
            <div key={k} className="flex items-center gap-2">
              <span className="w-11 shrink-0 text-[10px] text-text-low">{PARAM_LABEL[k] ?? k}</span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/6">
                <div className="h-full rounded-full bg-gradient-to-r from-accent-dim to-accent"
                  style={{ width: `${Math.min(100, (v / 255) * 100)}%`, transition: 'width .5s' }} />
              </div>
              <span className="w-7 shrink-0 text-right text-[10px] tabular-nums text-text-mid">{v}</span>
            </div>
          ))}
          {sync !== undefined && (
            <div className="pt-0.5 text-[10px] text-text-low">{sync ? '双侧同步开' : '双侧同步关'}</div>
          )}
          <div className="truncate pt-0.5 text-[10px] text-text-low" title={t.source}>
            来源 {t.source || '—'} · {t.applied_at || ''}
          </div>
        </div>
      ) : (
        <div className="text-[11px] text-text-low">无锁存效果——去扳机实验室或进游戏自动适配</div>
      )}
    </div>
  )
}

export default function Overview({ snap, events, onPanic }: {
  snap: EngineSnapshot | null
  events: EngineEvent[]
  onPanic: () => void
}) {
  const trig = snap?.state.triggers
  const rumble = snap?.state.rumble
  const online = snap?.device.online ?? false
  const mock = snap?.device.kind === 'mock'
  const batt = snap?.device.battery
  const adapt = deriveAdapt(snap)
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState('')

  // 电量走势：快照里电量变化时记一点，保留最近 40 个
  const [spark, setSpark] = useState<number[]>([])
  const lastBatt = useRef('')
  useEffect(() => {
    if (!batt) return
    const key = `${batt.level}:${batt.charging}`
    if (key === lastBatt.current) return
    lastBatt.current = key
    setSpark(s => [...s.slice(-39), batt.level])
  }, [batt])

  // 会话统计：从内存事件流派生（前端重启即清零，本来就是"本会话"口径）
  const stats = useMemo(() => {
    let sent = 0, ack = 0, fails = 0, autoswitch = 0
    for (const e of events) {
      if (e.kind === 'command') {
        if (e.result === 'sent') sent++
        else if (e.result === 'ack') ack++
        else if (e.result === 'nack' || e.result === 'timeout') fails++
      }
      if (e.kind === 'autoswitch') autoswitch++
    }
    return { sent, ack, fails, autoswitch }
  }, [events])

  const act = async (name: string, fn: () => Promise<unknown>, okMsg: string) => {
    setBusy(name)
    setMsg('')
    try {
      await fn()
      setMsg(okMsg)
    } catch (e) {
      setMsg(`✗ ${(e as Error).message}`)
    }
    setBusy('')
  }

  const KIND_DOT: Record<string, string> = {
    command: 'bg-white/25', state: 'bg-white/15', device: 'bg-accent',
    proxy: 'bg-warn', panic: 'bg-err', error: 'bg-err', autoswitch: 'bg-accent',
  }

  return (
    <div className="space-y-5">
      {/* ---------- 英雄区：设备仪表 + 适配状态 + 会话统计 ---------- */}
      <div className="card relative overflow-hidden p-6">
        <div className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full bg-accent/8 blur-3xl" />
        <div className="relative grid grid-cols-1 items-center gap-6 md:grid-cols-[auto_1fr_auto]">
          {/* 设备：连接环 + 电量 */}
          <div className="flex items-center gap-5">
            <div className="relative">
              <div className={`absolute inset-0 rounded-full ${online ? 'animate-ping bg-ok/15' : 'bg-err/10'}`}
                style={{ animationDuration: '2.4s' }} />
              <div className={`relative flex h-20 w-20 items-center justify-center rounded-full border-2 ${
                online ? 'border-ok/50 text-ok' : 'border-err/50 text-err'}`}>
                {online ? (mock ? <Monitor size={26} /> : <Usb size={26} />) : <Bluetooth size={26} />}
              </div>
            </div>
            <div>
              <div className="text-[17px] font-semibold">
                {online ? (mock ? 'Mock 虚拟手柄' : 'Apex 5 已连接') : '手柄未连接'}
              </div>
              <div className={`mt-0.5 flex items-center gap-1.5 text-[12px] ${online ? 'text-ok' : 'text-err'}`}>
                <span className={`h-1.5 w-1.5 rounded-full ${online ? 'animate-pulse bg-ok' : 'bg-err'}`} />
                {online ? 'HID 通道正常 · cmd 0x01/0x12/51' : '等待设备插入…'}
              </div>
              <div className="mt-1 flex items-center gap-3 text-[11px] text-text-low">
                {batt && <span>{batt.charging ? '充电中' : `电量 ${batt.level}/5`}</span>}
                <Spark data={spark} />
              </div>
            </div>
            {batt && <BatteryRing level={batt.level} charging={batt.charging} />}
          </div>

          {/* 适配状态（可视化原则：工具在干嘛必须一眼可见） */}
          <div className={`rounded-xl border p-4 text-center ${
            adapt.active ? 'border-accent/40 bg-accent/8' : 'border-border-soft bg-[#0d0d14]'}`}>
            <div className={`flex items-center justify-center gap-2 text-[13px] font-medium ${
              adapt.active ? 'text-accent' : 'text-text-mid'}`}>
              <Zap size={14} className={adapt.active ? 'animate-pulse' : ''} />
              {adapt.active ? '适配生效中' : '标准模式'}
            </div>
            <div className="mt-1.5 text-[12px] text-text-mid">
              {adapt.game && <span className="text-accent">🎮 {adapt.game}</span>}
              {adapt.uni && <span className="text-accent">通用震动联动</span>}
              {adapt.preset && <span className="text-accent">预设「{adapt.preset}」</span>}
              {!adapt.active && '无适配运行——进游戏会自动套用（如已绑定）'}
            </div>
            {snap?.proxy?.holder && (
              <div className={`mt-2 text-[11px] ${snap.proxy.holder === 'self' || snap.proxy.mild ? 'text-text-low' : 'text-warn'}`}>
                {snap.proxy.holder === 'self'
                  ? '代理权：本软件'
                  : snap.proxy.mild
                    ? '飞智空间站服务初始化中，稍后自动收回'
                    : `⚠ 被接管：${snap.proxy.detail || snap.proxy.holder}`}
              </div>
            )}
          </div>

          {/* 会话统计 */}
          <div className="grid grid-cols-2 gap-2 text-center md:grid-cols-1">
            {([['指令收发', `${stats.sent}`, '条'], ['ACK 确认', `${stats.ack}`, '条'],
              ['异常/超时', `${stats.fails}`, '条'], ['自动切换', `${stats.autoswitch}`, '次']] as const).map(
              ([label, v, unit]) => (
                <div key={label} className="rounded-lg border border-border-soft bg-[#0d0d14] px-4 py-1.5 text-left">
                  <span className="text-[11px] text-text-low">{label}</span>
                  <span className="float-right text-[13px] font-semibold tabular-nums text-text-hi">
                    {v}<span className="ml-0.5 text-[10px] font-normal text-text-low">{unit}</span>
                  </span>
                </div>
              ))}
          </div>
        </div>
      </div>

      {/* ---------- 扳机 + 震动实时状态 ---------- */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="card space-y-3 p-5 lg:col-span-2">
          <div className="flex items-center gap-2 text-[12px] text-text-mid">
            <Crosshair size={14} className="text-accent" /> 扳机锁存账本（固件当前效果）
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <TriggerRow t={trig?.left ?? null} side="left" />
            <TriggerRow t={trig?.right ?? null} side="right" />
          </div>
        </div>

        <div className="card flex flex-col p-5">
          <div className="mb-3 flex items-center gap-2 text-[12px] text-text-mid">
            <Waves size={14} className="text-accent" /> 马达实时输出
          </div>
          <div className="flex items-end justify-around">
            {(['l', 'r'] as const).map((k) => (
              <div key={k} className="text-center">
                <div className="mb-1 text-[11px] text-text-low">{k === 'l' ? '左马达' : '右马达'}</div>
                <div className="mx-auto h-24 w-9 overflow-hidden rounded-md bg-[#0d0d14]">
                  <div className="mt-auto w-full rounded-md bg-gradient-to-t from-accent-dim to-accent"
                    style={{
                      height: `${((rumble?.[k] ?? 0) / 255) * 100}%`,
                      boxShadow: (rumble?.[k] ?? 0) > 0 ? '0 0 12px rgba(34,211,238,.5)' : 'none',
                      transition: 'height .3s',
                    }} />
                </div>
                <div className="mt-1 text-[12px] tabular-nums text-text-mid">{rumble?.[k] ?? 0}</div>
              </div>
            ))}
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 border-t border-border-soft pt-3">
            <button className="btn justify-center !py-1 text-[12px]" disabled={busy === 'pulse'}
              onClick={() => act('pulse', () => api.pulse(), '✓ 脉冲已发，手上有感')}>
              震动一下
            </button>
            <button className="btn justify-center !py-1 text-[12px]" disabled={busy === 'lheavy'} title="只有左马达（低频）"
              onClick={() => act('lheavy', () => api.rumble(500, 0, 0.4), '✓ 左马达已测')}>
              左重
            </button>
            <button className="btn justify-center !py-1 text-[12px]" disabled={busy === 'rlight'} title="只有右马达（高频）"
              onClick={() => act('rlight', () => api.rumble(0, 500, 0.4), '✓ 右马达已测')}>
              右轻
            </button>
            <button className="btn justify-center !py-1 text-[12px]" disabled={busy === 'sine'}
              onClick={() => act('sine', () => api.sine(2, 4, 180), '✓ 2s 扫频测试')}>
              扫频测试
            </button>
          </div>
        </div>
      </div>

      {/* ---------- 快速操作 ---------- */}
      <div className="card flex flex-wrap items-center gap-3 p-4">
        <div className="flex items-center gap-2 text-[12px] text-text-mid">
          <Gauge size={14} className="text-accent" /> 快速操作
        </div>
        <button className="btn btn-danger !py-1 text-[12px]" onClick={onPanic}>
          <Eraser size={12} /> 手柄复位（保险丝）
        </button>
        <button className="btn !py-1 text-[12px]" disabled={busy === 'clear'}
          onClick={() => act('clear',
            () => Promise.all([api.clearTrigger('left'), api.clearTrigger('right')]),
            '✓ 扳机已恢复 Normal')}>
          清空扳机效果
        </button>
        {msg && <span className="text-[12px] text-text-mid">{msg}</span>}
        <span className="ml-auto text-[11px] text-text-low">
          效果均为锁存式，软件退出前自动复位；异常强杀后下次连接自动清理
        </span>
      </div>

      {/* ---------- 实时手柄（原手柄测试页并入）：示意图 + 拓展键 + 特殊键监听 ---------- */}
      <PadLiveCard events={events} />

      {/* ---------- 事件时间线 ---------- */}
      <div className="card p-5">
        <div className="mb-3 flex items-center gap-2 text-[12px] text-text-mid">
          <ScrollText size={14} className="text-accent" /> 事件时间线
          <span className="text-text-low">· 命令收发 / 代理权 / 自动切换 / 设备事件</span>
        </div>
        <div className="max-h-96 space-y-0 overflow-y-auto">
          {[...events].reverse().slice(0, 150).map((e, i) => {
            const auto = e.kind === 'autoswitch'
            return (
              <div key={i} className={`flex items-start gap-2.5 rounded px-2 py-1 hover:bg-white/3 ${auto ? 'bg-accent/5' : ''}`}>
                <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${KIND_DOT[e.kind] ?? 'bg-white/20'}`} />
                <span className="shrink-0 font-mono text-[11px] text-text-low">{e.ts}</span>
                <span className={`shrink-0 text-[12px] ${
                  e.kind === 'error' || e.kind === 'panic' ? 'text-err'
                    : e.kind === 'proxy' ? 'text-warn'
                    : auto ? 'text-accent' : 'text-text-mid'}`}>
                  {auto ? '自动切换' : e.kind === 'command' ? `cmd ${e.cmd ?? ''} ${e.result ?? ''}`
                    : e.kind === 'proxy' ? '代理权' : e.kind === 'state' ? '状态'
                    : e.kind === 'device' ? '设备' : e.kind === 'panic' ? '复位' : e.kind}
                </span>
                <span className="truncate text-[12px] text-text-low">
                  {typeof e.detail === 'string' ? e.detail : ''}
                  {typeof e.game === 'string' && e.game ? e.game : ''}
                  {typeof e.source === 'string' && e.source && !e.detail ? e.source : ''}
                </span>
              </div>
            )
          })}
          {events.length === 0 && (
            <div className="flex items-center gap-2 px-2 py-4 text-[12px] text-text-low">
              <Activity size={12} /> 暂无事件——去扳机实验室发个效果试试？
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
