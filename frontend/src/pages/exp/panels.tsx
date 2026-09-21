// 体验区功能面板（ADR-027）：15 项软件成品的交互 UI。
// 每个面板自治：自己拉数据、自己报错。真机类操作 mock 下会得到 400，按钮不禁用
// （用户能看见错误文案，比灰按钮更能说明「为什么不能点」）。
import { Component, useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { RefreshCw, AlertTriangle } from 'lucide-react'
import { api } from '../../api'

const BTN = 'rounded-md border border-border-soft px-2 py-1 text-[11px] transition-colors hover:border-accent/40 hover:text-accent'
const BTN_ACC = 'rounded-md border border-accent/40 bg-accent/10 px-2 py-1 text-[11px] text-accent transition-colors hover:bg-accent/20'
const BTN_DANGER = 'rounded-md border border-red-500/40 bg-red-500/10 px-2 py-1 text-[11px] text-red-300 transition-colors hover:bg-red-500/20'

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <span className="w-24 shrink-0 text-text-low">{label}</span>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  )
}

function useFlash(): [string, (ok: string, e?: unknown) => void] {
  const [msg, setMsg] = useState('')
  const flash = (ok: string, e?: unknown) => {
    const t = e ? `✗ ${e instanceof Error ? e.message : String(e)}` : ok
    setMsg(t)
    setTimeout(() => setMsg(''), 4000)
  }
  return [msg, flash]
}

function Err({ e }: { e: string }) {
  if (!e) return null
  return <div className="flex items-center gap-1 text-[11px] text-amber-300"><AlertTriangle size={12} /> {e}</div>
}

// k5 键表 id ↔ 名（与后端 profile.APEX5_KEYS 同源）
const KEY_NAMES: Record<number, string> = {
  0: '十字上', 1: '十字右', 2: '十字下', 3: '十字左', 4: 'A', 5: 'B', 6: '选择', 7: 'X', 8: 'Y',
  9: '开始', 10: 'LB', 11: 'RB', 12: 'LT', 13: 'RT', 14: 'L3', 15: 'R3', 18: 'M1', 19: 'M2',
  20: 'M3', 21: 'M4', 22: 'M5', 23: 'M6', 27: 'Home',
}
const TARGET_NAMES: Record<number, string> = {
  255: '透传', 254: '键盘', 32: '宏', 0: '十字上', 1: '十字右', 2: '十字下', 3: '十字左',
  4: 'A', 5: 'B', 6: '选择', 7: 'X', 8: 'Y', 9: '开始', 10: 'LB', 11: 'RB', 12: 'LT', 13: 'RT',
  14: 'L3', 15: 'R3', 27: 'Home',
}
const TURBO_MODES = ['关', '按住连发', '开关切换']

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

function CurveCanvas({ center, edge, p1, p2, bank }: {
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

function NoDev() {
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
const Safe = (C: React.FC): React.FC => props => (
  <PanelBoundary><C {...props} /></PanelBoundary>
)

// ==================== #1 体感瞄准（软件层） ====================
export function GyroPanel() {
  const [st, setSt] = useState<any>(null)
  const [msg, flash] = useFlash()
  const load = useCallback(() => { api.expGyro().then(setSt).catch(e => flash('', e)) }, [])
  useEffect(() => {
    load()
    const t = setInterval(load, 1000)
    return () => clearInterval(t)
  }, [load])
  if (!st) return <div className="space-y-2"><NoDev /><Err e={msg} /></div>
  const c = st.cfg
  const set = (patch: Record<string, unknown>) =>
    api.expGyroSet(patch).then((r: any) => { setSt(r); flash('✓ 已保存') }).catch(e => flash('', e))
  const g = st.stats?.last_gyro ?? [0, 0, 0]
  return (
    <div className="space-y-2">
      {/* 路标：三种「游戏用体感」的通道，防止重复造不存在的开关 */}
      <div className="rounded-md border border-border-soft bg-black/20 p-2 text-[10px] leading-relaxed text-text-low">
        <span className="text-text-mid">游戏怎么用上手柄体感？三条路：</span>
        ① 普通 XInput 游戏（不认体感）→ <b>固件层陀螺→摇杆</b>（体验区 #6，关软件也生效）或本面板软件层陀螺→鼠标；
        ② 原生体感游戏（Steam Input / DS5 移植 / NSO）→ <b>手柄拨硬件模式键切 Switch 模式</b>，
        切换后手柄在 USB 层变成任天堂设备（057e:2009），本工具和飞智空间站都看不见它，由游戏/Steam 自己接管——软件开关对此无解，不是功能缺失。
      </div>
      <Row label="总开关">
        <button className={c.enabled ? BTN_ACC : BTN} onClick={() => set({ enabled: !c.enabled })}>
          {c.enabled ? '开启中（点此关闭）' : '已关闭（点此开启）'}
        </button>
        <span className="text-[10px] text-text-low">软件层：工具运行时才生效，与固件层互斥</span>
      </Row>
      <Row label="激活方式">
        <select className="rounded border border-border-soft bg-black/30 px-1 py-0.5 text-[11px]"
          value={c.activation} onChange={e => set({ activation: e.target.value })}>
          <option value="always">常开</option>
          <option value="key">按住拓展键</option>
        </select>
        {c.activation === 'key' && (
          <select className="rounded border border-border-soft bg-black/30 px-1 py-0.5 text-[11px]"
            value={c.activation_key} onChange={e => set({ activation_key: e.target.value })}>
            {['m1', 'm2', 'm3', 'm4', 'lm', 'rm'].map(k => <option key={k} value={k}>{k.toUpperCase()}</option>)}
          </select>
        )}
      </Row>
      <Row label={`灵敏度 ${c.sens}`}>
        <input type="range" min={1} max={200} value={c.sens} className="w-40"
          onChange={e => set({ sens: +e.target.value })} />
      </Row>
      <Row label={`像素增益 ${c.gain}`}>
        <input type="range" min={2} max={40} step={0.5} value={c.gain} className="w-32"
          onChange={e => set({ gain: +e.target.value })} />
        <span className="text-[10px] text-text-low">手感待真机调（官方标定常数未公开）</span>
      </Row>
      <Row label="轴向">
        yaw
        <select className="rounded border border-border-soft bg-black/30 px-1 py-0.5 text-[11px]"
          value={c.yaw_axis} onChange={e => set({ yaw_axis: e.target.value })}>
          {['x', 'y', 'z'].map(a => <option key={a}>{a}</option>)}
        </select>
        pitch
        <select className="rounded border border-border-soft bg-black/30 px-1 py-0.5 text-[11px]"
          value={c.pitch_axis} onChange={e => set({ pitch_axis: e.target.value })}>
          {['x', 'y', 'z'].map(a => <option key={a}>{a}</option>)}
        </select>
        <label className="flex items-center gap-1"><input type="checkbox" checked={c.invert_x} onChange={e => set({ invert_x: e.target.checked })} /> 反转X</label>
        <label className="flex items-center gap-1"><input type="checkbox" checked={c.invert_y} onChange={e => set({ invert_y: e.target.checked })} /> 反转Y</label>
      </Row>
      <div className="text-[10px] text-text-low">
        陀螺实时 [{g.map((v: number) => v.toFixed(0)).join(', ')}] ｜ 流速率 ~{st.stats?.rate?.toFixed?.(0) ?? '—'}Hz ｜ 帧数 {st.stats?.frames ?? 0}
      </div>
      <Err e={msg} />
    </div>
  )
}

// ==================== #2 连发 Turbo ====================
export function TurboPanel() {
  const [p, setP] = useState<any>(null)
  const [msg, flash] = useFlash()
  const load = useCallback(() => { api.expProfile().then(setP).catch(e => flash('', e)) }, [flash])
  useEffect(() => { load() }, [load])
  if (!p) return <div className="space-y-2"><NoDev /><Err e={msg} /></div>
  const apply = (k: any) =>
    api.expTurbo(k.kid, k.turbo, k.freq)
      .then((r: any) => { setP(r); flash('✓ 已写入并保存（flash，稍慢属正常）') })
      .catch(e => { flash('', e); load() })
  return (
    <div className="space-y-1">
      <div className="text-[10px] text-text-low">
        固件级连发：写进档案 blob，关工具也生效。开启连发的键会自动映射回自身（官方同款）。
        档案：槽 {p.slot + 1}「{p.title}」（版本 {p.data_version}）
      </div>
      <div className="max-h-64 space-y-0.5 overflow-y-auto pr-1">
        {p.keys.map((k: any) => (
          <div key={k.kid} className="flex items-center gap-2 text-[11px]">
            <span className="w-14 text-text-mid">{k.name}</span>
            <span className="w-12 text-text-low">→{TARGET_NAMES[k.target] ?? k.target}</span>
            <select className="rounded border border-border-soft bg-black/30 px-1 py-0.5 text-[11px]"
              value={k.turbo}
              onChange={e => setP({ ...p, keys: p.keys.map((x: any) => x.kid === k.kid ? { ...x, turbo: +e.target.value } : x) })}>
              {TURBO_MODES.map((m, i) => <option key={i} value={i}>{m}</option>)}
            </select>
            <input type="number" min={1} max={255} value={k.freq} disabled={k.turbo === 0}
              className="w-14 rounded border border-border-soft bg-black/30 px-1 py-0.5 text-[11px] disabled:opacity-40"
              onChange={e => setP({ ...p, keys: p.keys.map((x: any) => x.kid === k.kid ? { ...x, freq: +e.target.value } : x) })} />
            <button className={BTN} onClick={() => apply(k)}>写入</button>
          </div>
        ))}
      </div>
      <Err e={msg} />
    </div>
  )
}

// ==================== #3 曲线编辑器 ====================
const STICK_PRESETS: Array<[string, number, number, number, number, number]> = [
  ['默认', 0, 0, 63, 63, 127],
  ['即时(快)', 1, 0, 64, 96, 127],
  ['延迟(慢)', 2, 0, 64, 32, 127],
]

export function StickCfgPanel() {
  const [p, setP] = useState<any>(null)
  const [side, setSide] = useState<'left' | 'right'>('left')
  const [msg, flash] = useFlash()
  const load = useCallback(() => { api.expProfile().then(setP).catch(e => flash('', e)) }, [flash])
  useEffect(() => { load() }, [load])
  if (!p) return <div className="space-y-2"><NoDev /><Err e={msg} /></div>
  const s = p.sticks[side] ?? { type: 0, center: 0, edge: 0, points: [63, 63, 127, 127], bank: [50, 62, 75, 87, 100, 112, 125, 137, 150], is_round: 0 }
  const pt: [[number, number], [number, number]] = [[s.points[0], s.points[1]], [s.points[2], s.points[3]]]
  const setLocal = (patch: any) => setP({ ...p, sticks: { ...p.sticks, [side]: { ...s, ...patch } } })
  const t = p.triggers[side] ?? { zero: 0, end: 255 }
  const saveStick = (extra: Record<string, unknown> = {}) =>
    api.expStick(side, {
      preset: null, center: s.center, edge: s.edge,
      p1: s.points.slice(0, 2), p2: s.points.slice(2, 4),
      is_round: !!s.is_round, ...extra,
    }).then((r: any) => { setP(r); flash('✓ 曲线已写入（核心块+bank 一起，固件只播 bank）') })
      .catch(e => { flash('', e); load() })
  const saveTrigger = (zero: number, end: number) =>
    api.expTriggerCurve(side, zero, end).then((r: any) => { setP(r); flash('✓ 扳机行程已写入') })
      .catch(e => { flash('', e); load() })
  return (
    <div className="space-y-2">
      <Row label="侧">
        {(['left', 'right'] as const).map(x => (
          <button key={x} className={side === x ? BTN_ACC : BTN} onClick={() => setSide(x)}>
            {x === 'left' ? '左摇杆' : '右摇杆'}
          </button>
        ))}
        <span className="text-[10px] text-text-low">
          {s.is_not_stick ? '⚠ 此摇杆被映射走（center=127 哨兵）' : `类型 ${s.type}（0默认/1快/2慢/3自定义）`}
        </span>
      </Row>
      <div className="flex gap-3">
        <CurveCanvas center={s.center} edge={s.edge} p1={pt[0]} p2={pt[1]}
          bank={s.bank.map((b: number) => b)} />
        <div className="flex-1 space-y-1.5">
          <Row label={`死区 ${s.center}`}>
            <input type="range" min={0} max={100} value={s.center} className="w-32"
              onChange={e => setLocal({ center: +e.target.value })} />
          </Row>
          <Row label={`边缘收缩 ${s.edge}`}>
            <input type="range" min={0} max={100} value={s.edge} className="w-32"
              onChange={e => setLocal({ edge: +e.target.value })} />
          </Row>
          <Row label="控制点">
            {pt.map((v, i) => (
              <span key={i} className="flex items-center gap-1">
                P{i + 1}(<input type="number" min={0} max={127} value={v[0]} className="w-11 rounded border border-border-soft bg-black/30 px-0.5 text-[11px]"
                  onChange={e => setLocal({ points: i === 0 ? [+e.target.value, v[1], pt[1][0], pt[1][1]] : [pt[0][0], pt[0][1], +e.target.value, v[1]] })} />,
                <input type="number" min={0} max={127} value={v[1]} className="w-11 rounded border border-border-soft bg-black/30 px-0.5 text-[11px]"
                  onChange={e => setLocal({ points: i === 0 ? [v[0], +e.target.value, pt[1][0], pt[1][1]] : [pt[0][0], pt[0][1], v[0], +e.target.value] })} />)
              </span>
            ))}
            <label className="flex items-center gap-1">
              <input type="checkbox" checked={!!s.is_round} onChange={e => setLocal({ is_round: e.target.checked ? 1 : 0 })} /> 圆形化
            </label>
          </Row>
        </div>
      </div>
      <Row label="预设">
        {STICK_PRESETS.map(([name, type, c, x, y, e]) => (
          <button key={name} className={BTN}
            onClick={() => api.expStick(side, { preset: type, center: c, edge: e, p1: [x, y] })
              .then((r: any) => { setP(r); flash(`✓ 预设「${name}」已写入`) }).catch(ex => flash('', ex))}>
            {name}
          </button>
        ))}
        <button className={BTN_ACC} onClick={() => saveStick()}>写入自定义曲线</button>
      </Row>
      <Row label={`扳机行程 ${t.zero}..${t.end}`}>
        <input type="range" min={0} max={200} value={t.zero} className="w-28"
          onChange={e => saveTrigger(+e.target.value, Math.max(+e.target.value + 5, t.end))} />
        <input type="range" min={t.zero + 5} max={255} value={t.end} className="w-28"
          onChange={e => saveTrigger(t.zero, +e.target.value)} />
        <span className="text-[10px] text-text-low">拖动即写（线性镜像控制点，官方唯一组合）</span>
      </Row>
      <Err e={msg} />
    </div>
  )
}

// ==================== #4 设备设置页 ====================
const BITS = ['快切', 'XboxHome', '体感去抖', '映射开关', '摇杆防抖', '自动校准', '摇杆回中', '状态栏常亮']

export function DevCfgPanel() {
  const [d, setD] = useState<any>(null)
  const [nick, setNick] = useState('')
  const [msg, flash] = useFlash()
  const load = useCallback(() => { api.expDevCfg().then((r: any) => { setD(r); setNick(r.nickname ?? '') }).catch(e => flash('', e)) }, [flash])
  useEffect(() => { load() }, [load])
  if (!d) return <div className="space-y-2"><NoDev /><Err e={msg} /></div>
  const f = d.settings?.flags ?? {}
  const setBit = (sub: number, on: boolean) =>
    api.expSetting('bit', { sub, on }).then((r: any) => { setD({ ...d, settings: r.settings }); flash('✓ 已写入并读回复核') }).catch(e => flash('', e))
  const setVal = (op: string, value: number) =>
    api.expSetting(op, { value }).then((r: any) => { setD({ ...d, settings: r.settings }); flash('✓ 已写入并读回复核') }).catch(e => flash('', e))
  const s = d.settings ?? {}
  return (
    <div className="space-y-2">
      <Row label="版本">
        <span className="text-[10px] text-text-mid">
          {Object.entries(d.versions ?? {}).map(([k, v]) => `${k}:${v ?? '—'}`).join('  ')}
        </span>
      </Row>
      <Row label="功能开关">
        {BITS.map((n, i) => (
          <label key={n} className={`flex items-center gap-1 ${f.usable?.[n] ? '' : 'opacity-35'}`}
            title={f.usable?.[n] ? '' : '固件不支持'}>
            <input type="checkbox" disabled={!f.usable?.[n]} checked={!!f.enabled?.[n]}
              onChange={e => setBit(i + 1, e.target.checked)} /> {n}
          </label>
        ))}
      </Row>
      <Row label="息屏常显">
        <label className="flex items-center gap-1">
          <input type="checkbox" disabled={!f.extra_usable?.['息屏常显']} checked={!!f.extra_enabled?.['息屏常显']}
            onChange={e => setBit(9, e.target.checked)} /> 屏幕熄灭时常显（k5 视固件而定）
        </label>
      </Row>
      <Row label="回报率">
        <select className="rounded border border-border-soft bg-black/30 px-1 py-0.5 text-[11px]"
          value={s.rate_raw ?? 0}
          onChange={e => setVal('rate', +e.target.value)}>
          {(s.rate_raw === 0
            ? [{ raw: 0, hz: '默认(当前)' } as any]
            : [1, 2, 4, 8].map((r, i) => ({ raw: r, hz: [1000, 500, 250, 125][i] }))
          ).map((o: any) => <option key={o.raw} value={o.raw}>{o.hz}</option>)}
        </select>
        {s.rate_raw === 0 && <span className="text-[10px] text-amber-300">k5 读回 0=默认：写未知档有风险，选具体值再改</span>}
      </Row>
      <Row label="摇杆精度">
        <select className="rounded border border-border-soft bg-black/30 px-1 py-0.5 text-[11px]" value={s.precision ?? 0}
          onChange={e => setVal('precision', +e.target.value)}>
          {[[0, '默认'], [1, '8bit'], [2, '10bit'], [3, '12bit'], [4, '9bit'], [5, '11bit'], [6, '14bit'], [7, '16bit']]
            .map(([v, n]) => <option key={v as number} value={v}>{n}</option>)}
        </select>
      </Row>
      <Row label="灵敏度">
        <select className="rounded border border-border-soft bg-black/30 px-1 py-0.5 text-[11px]" value={s.sensitivity ?? 17}
          onChange={e => setVal('sensitivity', +e.target.value)}>
          {[14, 15, 16, 17, 18, 19, 20].map((v, i) => <option key={v} value={v}>{['最高', '较高', '中高', '中', '中低', '较低', '最低'][i]}</option>)}
        </select>
      </Row>
      <Row label="睡眠">
        <input type="number" min={0} max={60} defaultValue={s.sleep_min ?? 0}
          className="w-16 rounded border border-border-soft bg-black/30 px-1 py-0.5 text-[11px]" id="exp-sleep" />
        <button className={BTN} onClick={() => {
          const el = document.getElementById('exp-sleep') as HTMLInputElement
          setVal('sleep', +el.value)
        }}>分钟（0=永不）写入</button>
      </Row>
      <Row label="昵称">
        <input value={nick} maxLength={26} placeholder="手柄没起过名"
          className="w-40 rounded border border-border-soft bg-black/30 px-1 py-0.5 text-[11px]"
          onChange={e => setNick(e.target.value)} />
        <button className={BTN} onClick={() => api.expNickname(nick).then(load).catch(e => flash('', e))}>写入</button>
      </Row>
      <Row label="档案名">
        <button className={BTN} onClick={() => {
          const t = window.prompt('新档案名（显示在手柄屏幕，≤10 个汉字）')
          if (t) api.expTitle(t).then((r: any) => { flash(`✓ 当前槽已改名「${r.title}」`) }).catch(e => flash('', e))
        }}>改当前槽标题</button>
      </Row>
      <Row label="重启">
        <button className={BTN_DANGER} onClick={() => {
          if (window.confirm('重启手柄？（会短暂掉线重连）'))
            api.expReboot().then(() => flash('✓ 重启指令已发')).catch(e => flash('', e))
        }}>手柄重启</button>
      </Row>
      <Err e={msg} />
    </div>
  )
}

// ==================== #5 共存仲裁 ====================
export function ArbitrationPanel() {
  const [o, setO] = useState<any>(null)
  const [msg, flash] = useFlash()
  const load = useCallback(() => { api.expOwner().then((r: any) => setO(r.owner)).catch(e => flash('', e)) }, [flash])
  useEffect(() => { load() }, [load])
  const F = ['xinput', 'private_data', 'keyboard', 'mouse', 'third_party']
  return (
    <div className="space-y-2">
      <Row label="占用方">
        <button className={BTN} onClick={load}><RefreshCw size={11} /> 重新读取</button>
        {o && <span className="text-[11px] text-text-mid">
          标签：<b className="text-text-hi">{o.control_by ?? '（无名）'}</b>
        </span>}
      </Row>
      {o && (
        <div className="text-[10px] text-text-low">
          {F.map(k => `${k}=${o[k]}`).join('  ')}
        </div>
      )}
      <Row label="夺回">
        <button className={BTN_ACC} onClick={() =>
          api.expAcquire().then((r: any) => { setO(r.owner); flash('✓ cmd28 已发（设备实名申请，语义待真机核）') }).catch(e => flash('', e))
        }>发送申请（cmd28，报上名号）</button>
        <span className="text-[10px] text-text-low">配合侧栏的「夺回控制权」一起用：那边重放账本，这边让设备记住是谁</span>
      </Row>
      <Err e={msg} />
    </div>
  )
}

// ==================== #6 体感映射（固件层） ====================
const MOTION_TARGETS = [['0', '关闭'], ['1', '左摇杆（赛车）'], ['2', '右摇杆（射击）']]
const MOTION_KEYS: Array<[number, string]> = [
  [255, '无激活键'],
  ...Object.entries(KEY_NAMES).map(([k, v]): [number, string] => [+k, v]),
]

export function GyroFwPanel() {
  const [p, setP] = useState<any>(null)
  const [msg, flash] = useFlash()
  const load = useCallback(() => { api.expProfile().then(setP).catch(e => flash('', e)) }, [flash])
  useEffect(() => { load() }, [load])
  if (!p) return <div className="space-y-2"><NoDev /><Err e={msg} /></div>
  const m = p.motion
  const save = (patch: any) =>
    api.expMotion({ ...m, ...patch }).then((r: any) => { setP(r); flash('✓ motion 块已写入并保存') }).catch(e => { flash('', e); load() })
  return (
    <div className="space-y-2">
      <div className="text-[10px] text-text-low">
        固件直通：写 blob 137 motion 块，关工具也生效、零软件延迟。<b className="text-amber-300">与软件层体感互斥</b>。
        当前 target={m.target}（0关/1左摇杆/2右摇杆）
      </div>
      <Row label="映射到">
        {MOTION_TARGETS.map(([v, n]) => (
          <button key={v} className={+m.target === +v ? BTN_ACC : BTN}
            onClick={() => save({ target: +v })}>{n}</button>
        ))}
      </Row>
      {m.target !== 0 && (
        <>
          <Row label="激活键">
            <select className="rounded border border-border-soft bg-black/30 px-1 py-0.5 text-[11px]"
              value={m.enable_key} onChange={e => save({ enable_key: +e.target.value })}>
              {MOTION_KEYS.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
            </select>
            <select className="rounded border border-border-soft bg-black/30 px-1 py-0.5 text-[11px]"
              value={m.enable_type} onChange={e => save({ enable_type: +e.target.value })}>
              <option value={0}>点按切换</option>
              <option value={1}>按住生效</option>
            </select>
          </Row>
          <Row label={`死区 ${m.dead_zone}`}>
            <input type="range" min={0} max={100} value={m.dead_zone} className="w-32"
              onChange={e => save({ dead_zone: +e.target.value })} />
          </Row>
          <Row label={`灵敏度 X/Y ${m.sens_x}/${m.sens_y}`}>
            <input type="range" min={0} max={100} value={m.sens_x} className="w-28" onChange={e => save({ sens_x: +e.target.value })} />
            <input type="range" min={0} max={100} value={m.sens_y} className="w-28" onChange={e => save({ sens_y: +e.target.value })} />
          </Row>
        </>
      )}
      <Err e={msg} />
    </div>
  )
}

// ==================== #7 摇杆→鼠标/键盘 ====================
export function StickMapPanel() {
  const [st, setSt] = useState<any>(null)
  const [msg, flash] = useFlash()
  const load = useCallback(() => { api.expStickMap().then(setSt).catch(e => flash('', e)) }, [])
  useEffect(() => { load() }, [load])
  if (!st) return <div className="space-y-2"><NoDev /><Err e={msg} /></div>
  const c = st.cfg
  const set = (patch: Record<string, unknown>) =>
    api.expStickMapSet(patch).then((r: any) => { setSt(r); flash('✓ 已保存') }).catch(e => flash('', e))
  return (
    <div className="space-y-2">
      <Row label="总开关">
        <button className={c.enabled ? BTN_ACC : BTN} onClick={() => set({ enabled: !c.enabled })}>
          {c.enabled ? '开启中（点此关闭）' : '已关闭（点此开启）'}
        </button>
        <span className="text-[10px] text-text-low">软件层：工具运行时注入，摇杆原生输出仍在（游戏可能双输入）</span>
      </Row>
      <Row label="摇杆">
        {['left', 'right'].map(x => (
          <button key={x} className={c.stick === x ? BTN_ACC : BTN} onClick={() => set({ stick: x })}>
            {x === 'left' ? '左' : '右'}
          </button>
        ))}
      </Row>
      <Row label="映射为">
        {['keys', 'mouse'].map(x => (
          <button key={x} className={c.mode === x ? BTN_ACC : BTN} onClick={() => set({ mode: x })}>
            {x === 'keys' ? '键盘方向键' : '鼠标'}
          </button>
        ))}
      </Row>
      {c.mode === 'keys' ? (
        <Row label="键位">
          {(['up', 'down', 'left', 'right'] as const).map(d => (
            <span key={d} className="flex items-center gap-1">
              {d}
              <input value={c.keys[d]} maxLength={1}
                className="w-8 rounded border border-border-soft bg-black/30 px-1 py-0.5 text-center text-[11px]"
                onChange={e => set({ keys: { ...c.keys, [d]: e.target.value.toLowerCase() } })} />
            </span>
          ))}
          <span className="text-[10px] text-text-low">已按：{st.stats.pressed.join('+') || '—'}</span>
        </Row>
      ) : (
        <Row label={`速度 ${c.sens}`}>
          <input type="range" min={5} max={120} value={c.sens} className="w-40"
            onChange={e => set({ sens: +e.target.value })} />
          <span className="text-[10px] text-text-low">摇杆实时 [{st.stats.last_xy.map((v: number) => v.toFixed(0)).join(', ')}]</span>
        </Row>
      )}
      <Row label={`死区 ${c.deadzone}`}>
        <input type="range" min={500} max={8000} step={100} value={c.deadzone} className="w-40"
          onChange={e => set({ deadzone: +e.target.value })} />
      </Row>
      <Err e={msg} />
    </div>
  )
}

// ==================== #8 Mod 灯效桥 ====================
export function RgbBridgePanel() {
  const [st, setSt] = useState<any>(null)
  const [msg, flash] = useFlash()
  const load = useCallback(() => { api.expRgb().then(setSt).catch(e => flash('', e)) }, [])
  useEffect(() => {
    load()
    const t = setInterval(load, 2000)
    return () => clearInterval(t)
  }, [load])
  if (!st) return <div className="space-y-2"><NoDev /><Err e={msg} /></div>
  const toggle = () =>
    api.expRgbSet(!st.enabled, st.port).then((r: any) => { setSt(r); flash(r.enabled ? '✓ 桥已启动' : '已停止') }).catch(e => flash('', e))
  const testColor = (rgb: number[]) =>
    api.expRgbTest(rgb).then((r: any) => { setSt(r); flash(rgb[0] ? '✓ 已发红' : rgb[1] ? '✓ 已发绿' : '✓ 已发蓝') }).catch(e => flash('', e))
  return (
    <div className="space-y-2">
      <Row label="监听">
        <button className={st.enabled ? BTN_ACC : BTN} onClick={toggle}>
          {st.enabled ? `运行中 127.0.0.1:${st.port}（点此停止）` : `已停止（点此启动 :${st.port}）`}
        </button>
        <span className="text-[10px] text-text-low">DSX 等往 7878 发的 RGB 颜色 → 翻译成手柄灯效（官方静默丢弃的部分）</span>
      </Row>
      {st.enabled && (
        <Row label="测试色">
          <button className="h-6 w-9 rounded border border-red-500/50 bg-red-600/70 text-[10px]" onClick={() => testColor([255, 0, 0])}>红</button>
          <button className="h-6 w-9 rounded border border-emerald-500/50 bg-emerald-600/70 text-[10px]" onClick={() => testColor([0, 255, 0])}>绿</button>
          <button className="h-6 w-9 rounded border border-blue-500/50 bg-blue-600/70 text-[10px]" onClick={() => testColor([0, 0, 255])}>蓝</button>
          <button className={BTN} onClick={() => testColor([0, 0, 0])}>熄灯</button>
          <span className="text-[10px] text-text-low">手柄连着工具时点一下，灯应该立即变色——这就是桥的效果</span>
        </Row>
      )}
      <Row label="游戏事件闪灯">
        <button
          className={st.flash_enabled ? BTN_ACC : BTN}
          onClick={() => api.expRgbFlash(!st.flash_enabled, [255, 0, 0]).then((r: any) => { setSt(r); flash(r.flash_enabled ? '✓ 已开启' : '已关闭') }).catch(e => flash('', e))}>
          {st.flash_enabled ? '开启中（游戏 Mod 扳机事件时闪红）' : '已关闭（点此开启）'}
        </button>
        <span className="text-[10px] text-text-low">普通游戏不会发灯色；装了 Mod 的游戏（Mod 管家）事件流经过工具时灯闪一下</span>
      </Row>
      {st.stats?.note && <div className="text-[11px] text-amber-300"><AlertTriangle size={12} className="inline" /> {st.stats.note}</div>}
      <div className="text-[10px] text-text-low">
        收包 {st.stats?.packets ?? 0} ｜ 应用 {st.stats?.applied ?? 0}（限频 ≥1s，同色不重写）｜ 未识别 {st.stats?.unknown ?? 0}
        {st.stats?.last_rgb && ` ｜ 最近 RGB(${st.stats.last_rgb.join(',')})`}
        {st.stats?.last_error && ` ｜ 错误: ${st.stats.last_error}`}
      </div>
      <Err e={msg} />
    </div>
  )
}

// ==================== #9 摇杆体检 ====================
export function DiagnosticsPanel() {
  const [d, setD] = useState<any>(null)
  const [msg, flash] = useFlash()
  const ref = useRef<HTMLCanvasElement>(null)
  const load = useCallback(() => { api.expDiagData().then(setD).catch(e => flash('', e)) }, [])
  useEffect(() => { load() }, [load])
  useEffect(() => {
    if (!d?.running) { const t = setTimeout(load, 700); return () => clearTimeout(t) }
    const t = setInterval(load, 400)
    return () => clearInterval(t)
  }, [d?.running, load])
  useEffect(() => {
    const cv = ref.current
    if (!cv || !d?.points) return
    const g = cv.getContext('2d')
    if (!g) return
    const W = cv.width, H = cv.height
    g.fillStyle = 'rgba(0,0,0,0.25)'
    g.fillRect(0, 0, W, H)
    g.strokeStyle = 'rgba(255,255,255,0.15)'
    g.beginPath(); g.moveTo(W / 2, 0); g.lineTo(W / 2, H); g.moveTo(0, H / 2); g.lineTo(W, H / 2); g.stroke()
    const M = 32000
    for (const [c, col] of [[0, '#67e8f9'], [2, '#fbbf24']] as Array<[number, string]>) {
      g.fillStyle = col
      for (const p of d.points) {
        const x = W / 2 + (p[c] / M) * (W / 2 - 4)
        const y = H / 2 + (p[c + 1] / M) * (H / 2 - 4)
        g.fillRect(x, y, 1.5, 1.5)
      }
    }
  }, [d])
  const sample = () =>
    api.expDiag('sample', { seconds: 5 }).then(() => { flash('采样中：匀速画圈 5 秒…'); setTimeout(load, 300) }).catch(e => flash('', e))
  return (
    <div className="space-y-2">
      <Row label="采样">
        <button className={BTN_ACC} onClick={sample}>采 5 秒（画圈）</button>
        {d?.rate_hz && <span className="text-[10px] text-text-low">回报率 ~{d.rate_hz}Hz（{d.n} 样本）</span>}
      </Row>
      <canvas ref={ref} width={340} height={170} className="rounded border border-border-soft" />
      {d?.left && (
        <div className="text-[10px] text-text-low">
          左 [{d.left.min_x},{d.left.max_x}]×[{d.left.min_y},{d.left.max_y}] 中心({d.left.center_x.toFixed(0)},{d.left.center_y.toFixed(0)})
          {'  '}右 [{d.right.min_x},{d.right.max_x}]×[{d.right.min_y},{d.right.max_y}] 中心({d.right.center_x.toFixed(0)},{d.right.center_y.toFixed(0)})
          {'  '}(青=左 黄=右)
        </div>
      )}
      <Row label="校准">
        <button className={BTN} onClick={() => api.expDiag('adccalib', { stage: 'start' }).then(() => flash('✓ 校准开始：松开摇杆别碰')).catch(e => flash('', e))}>ADC 开始</button>
        <button className={BTN} onClick={() => api.expDiag('adccalib', { stage: 'stop' }).then(() => flash('✓ 校准结束')).catch(e => flash('', e))}>结束</button>
        <span className="text-[10px] text-amber-300">报文细节待真机核（cmd240）</span>
      </Row>
      <Row label="自动校准">
        <button className={BTN} onClick={() => api.expDiag('autocal', { on: true }).then(() => flash('✓ 已开')).catch(e => flash('', e))}>开</button>
        <button className={BTN} onClick={() => api.expDiag('autocal', { on: false }).then(() => flash('已关')).catch(e => flash('', e))}>关</button>
        <span className="text-[10px] text-text-low">= 设置块 sub6（摇杆自动校准）</span>
      </Row>
      <Err e={msg} />
    </div>
  )
}

// ==================== #10 四槽快切 ====================
export function SlotsPanel() {
  const [d, setD] = useState<any>(null)
  const [msg, flash] = useFlash()
  const load = useCallback(() => { api.expSlots().then(setD).catch(e => flash('', e)) }, [flash])
  useEffect(() => { load() }, [load])
  if (!d) return <div className="space-y-2"><NoDev /><Err e={msg} /></div>
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-2">
        {[0, 1, 2, 3].map(i => (
          <button key={i} className={`rounded-md border p-2 text-left text-[11px] ${d.active === i ? 'border-accent/60 bg-accent/10' : 'border-border-soft hover:border-accent/40'}`}
            onClick={() => api.expSlotApply(i).then(() => { flash(`✓ 已切到槽 ${i + 1}`); load() }).catch(e => flash('', e))}>
            <div className="font-semibold text-text-hi">槽 {i + 1}{d.active === i ? ' ｜ 当前' : ''}</div>
            <div className="text-text-mid">{d.titles[i] || '（未命名）'}</div>
          </button>
        ))}
      </div>
      <div className="text-[10px] text-text-low">
        点卡片即切（162 应用，立即生效不落 flash）。手柄端 Fn+十字键 也能切——「快切」开关在设备设置页。
      </div>
      <Err e={msg} />
    </div>
  )
}

// ==================== #11 分享码 ====================
export function ShareCodePanel() {
  const [code, setCode] = useState('')
  const [dec, setDec] = useState<any>(null)
  const [msg, flash] = useFlash()
  return (
    <div className="space-y-2">
      <Row label="导出">
        <button className={BTN_ACC} onClick={() =>
          api.expShareEncode('profile').then((r: any) => { setCode(r.code); flash('✓ 当前槽已编码（zlib+base62，含校验）') }).catch(e => flash('', e))
        }>编码当前槽 → 分享码</button>
      </Row>
      <textarea value={code} onChange={e => setCode(e.target.value)} rows={3}
        placeholder="APX5-… 分享码贴这里（导入导出同一框）"
        className="w-full rounded border border-border-soft bg-black/30 p-2 font-mono text-[10px] break-all" />
      <Row label="导入">
        <button className={BTN} onClick={() =>
          api.expShareDecode(code).then((r: any) => { setDec(r); flash('✓ 解码成功，检查预览后再应用') }).catch(e => flash('', e))
        }>解码预览</button>
        {dec && <button className={BTN_DANGER} onClick={() =>
          api.expShareApply(code).then(() => flash('✓ 已写入当前槽（覆盖！）')).catch(e => flash('', e))
        }>应用到当前槽（覆盖）</button>}
      </Row>
      {dec?.profile && (
        <div className="text-[10px] text-text-low">
          预览：槽{dec.slot !== undefined ? `（源槽 ${dec.slot + 1}）` : ''}「{dec.profile.title}」版本 {dec.profile.data_version} ｜
          {' '}连发键 {dec.profile.keys.filter((k: any) => k.turbo).map((k: any) => k.name).join(',') || '无'} ｜
          {' '}体感 target={dec.profile.motion.target}
        </div>
      )}
      <Err e={msg} />
    </div>
  )
}

// ==================== #12 Switch 第二银行 ====================
export function SwitchBankPanel() {
  const [d, setD] = useState<any>(null)
  const [slot, setSlot] = useState(0)
  const [msg, flash] = useFlash()
  const load = useCallback(() => { api.expSlots().then(setD).catch(e => flash('', e)) }, [flash])
  useEffect(() => { load() }, [load])
  if (!d) return <div className="space-y-2"><NoDev /><Err e={msg} /></div>
  return (
    <div className="space-y-2">
      <Row label="源槽">
        {[0, 1, 2, 3].map(i => (
          <button key={i} className={slot === i ? BTN_ACC : BTN} onClick={() => setSlot(i)}>
            槽 {i + 1}（{d.titles[i] || '未命名'}）
          </button>
        ))}
      </Row>
      <Row label="同步">
        <button className={BTN_DANGER} onClick={() =>
          api.expSwitchSync(slot).then((r: any) => flash(`✓ 已写入 Switch 银行槽 ${r.switch_slot}（171 落 flash，稍慢）`)).catch(e => flash('', e))
        }>写入 Switch 银行（槽 {slot + 4}）</button>
        <span className="text-[10px] text-text-low">键盘映射自动回透传、被映射走的摇杆回直通（normalise 同官方）</span>
      </Row>
      <Err e={msg} />
    </div>
  )
}

// ==================== #13 握把震动 ====================
function SideVib({ s, set }: { s: any; set: (p: any) => void }) {
  return (
    <div className="space-y-1">
      <label className="flex items-center gap-1 text-[11px]">
        <input type="checkbox" checked={!!s.on} onChange={e => set({ on: e.target.checked })} /> 启用
      </label>
      {(['min', 'max', 'scale'] as const).map(k => (
        <Row key={k} label={`${k} ${s[k] ?? 0}`}>
          <input type="range" min={0} max={255} value={s[k] ?? 0} className="w-36"
            onChange={e => set({ [k]: +e.target.value })} />
        </Row>
      ))}
    </div>
  )
}

export function GripVibPanel() {
  const [p, setP] = useState<any>(null)
  const [msg, flash] = useFlash()
  const load = useCallback(() => { api.expProfile().then(setP).catch(e => flash('', e)) }, [flash])
  useEffect(() => { load() }, [load])
  if (!p) return <div className="space-y-2"><NoDev /><Err e={msg} /></div>
  const g = p.grip_vib
  const save = (ng: any) =>
    api.expGripVib(ng.enabled, ng.left, ng.right).then((r: any) => { setP(r); flash('✓ 握把震动已写入') }).catch(e => { flash('', e); load() })
  const set = (patch: any) => { const ng = { ...g, ...patch }; setP({ ...p, grip_vib: ng }); return ng }
  return (
    <div className="space-y-2">
      <Row label="总开关">
        <button className={g.enabled ? BTN_ACC : BTN} onClick={() => save(set({ enabled: !g.enabled }))}>
          {g.enabled ? '开启中' : '已关闭'}
        </button>
        <button className={BTN} onClick={() =>
          save(set({ left: { ...g.left, on: true, min: 0, max: 255, scale: 128 }, right: { ...g.right, on: true, min: 0, max: 255, scale: 128 } }))
        }>「Xbox 感」预设（50%）</button>
        <span className="text-[10px] text-text-low">Min/Max 是触发窗口，Scale 是输出比例</span>
      </Row>
      <div className="grid grid-cols-2 gap-4">
        {(['left', 'right'] as const).map(side => (
          <div key={side} className="space-y-1">
            <div className="text-[11px] font-semibold text-text-mid">{side === 'left' ? '左握把' : '右握把'}</div>
            <SideVib s={g[side]} set={patch => set({ [side]: { ...g[side], ...patch } })} />
          </div>
        ))}
      </div>
      <Row label="">
        <button className={BTN_ACC} onClick={() => save(g)}>写入</button>
      </Row>
      <Err e={msg} />
    </div>
  )
}

// ==================== #14 屏幕补全 ====================
export function ScreenPlusPanel() {
  const [msg, flash] = useFlash()
  const [busy, setBusy] = useState(false)
  const toggle = (sub: number, on: boolean, name: string) => {
    setBusy(true)
    api.expSetting('bit', { sub, on })
      .then(() => flash(`✓ ${name} 已${on ? '开' : '关'}`))
      .catch(e => flash('', e))
      .finally(() => setBusy(false))
  }
  return (
    <div className="space-y-2">
      <Row label="状态栏">
        <button className={BTN} disabled={busy} onClick={() => toggle(8, true, '状态栏常亮')}>常亮开</button>
        <button className={BTN} disabled={busy} onClick={() => toggle(8, false, '状态栏常亮')}>关</button>
        <span className="text-[10px] text-text-low">= 设置块 sub8（屏幕页也有同款）</span>
      </Row>
      <Row label="动画常亮">
        <button className={BTN} disabled={busy} onClick={() => toggle(9, true, '动画常亮')}>开</button>
        <button className={BTN} disabled={busy} onClick={() => toggle(9, false, '动画常亮')}>关</button>
        <span className="text-[10px] text-text-low">= sub9（实测语义可能反转，以真机为准）</span>
      </Row>
      <Row label="GIF 裁剪">
        <span className="text-[10px] text-text-low">帧范围裁剪和恢复出厂动画在「屏幕」页（上传前选帧区间）</span>
      </Row>
      <Err e={msg} />
    </div>
  )
}

// ==================== #15 危险区 ====================
export function FactoryResetPanel() {
  const [msg, flash] = useFlash()
  const [confirm, setConfirm] = useState('')
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1 text-[11px] text-red-300">
        <AlertTriangle size={12} /> 恢复出厂前会自动全量备份（四槽 blob + 灯表 → 数据文件夹 backup_时间戳\）。
        单槽=出厂档案写回（<b>灯光不动、k5 宏会被清</b>）；全部=cmd175（四槽连名字全重置）。
      </div>
      <Row label="确认">
        <input value={confirm} placeholder="输入 RESET"
          className="w-32 rounded border border-border-soft bg-black/30 px-1 py-0.5 text-[11px]"
          onChange={e => setConfirm(e.target.value)} />
      </Row>
      <div className="grid grid-cols-4 gap-2">
        {[0, 1, 2, 3].map(i => (
          <button key={i} className={BTN_DANGER} disabled={confirm !== 'RESET'}
            onClick={() => api.expFactorySlot(i, 'RESET')
              .then(() => flash(`✓ 槽 ${i + 1} 已恢复出厂`)).catch(e => flash('', e))}>
            重置槽 {i + 1}
          </button>
        ))}
      </div>
      <Row label="全部">
        <button className={BTN_DANGER} disabled={confirm !== 'RESET-ALL'}
          onClick={() => api.expFactoryAll('RESET-ALL')
            .then(() => flash('✓ 四槽已全部恢复出厂（重连后生效）')).catch(e => flash('', e))}>
          重置全部（输入 RESET-ALL 解锁）
        </button>
      </Row>
      <Err e={msg} />
    </div>
  )
}

// ==================== #16 模拟游戏场 ====================
// 自己给自己当一个「游戏」：四个测试场覆盖全功能链路。
// 扳机场/灯场的事件走真实 UDP 链路（DSX 协议→ingress→cmd51；RGB→灯效桥→灯表），
// 与真游戏 Mod 同一条路；靶场/键盘场在本地跑，闭环测体感瞄准、摇杆映射、连发、宏。

// 靶场：鼠标轨迹 + 随机靶子打分——体感瞄准/摇杆转鼠标的闭环验证
function AimRange() {
  const ref = useRef<HTMLCanvasElement>(null)
  const [score, setScore] = useState(0)
  const [shots, setShots] = useState(0)
  const sim = useRef({
    trail: [] as Array<{ x: number; y: number; t: number }>,
    targets: [] as Array<{ x: number; y: number; r: number; born: number }>,
    mx: 0, my: 0,
  })
  useEffect(() => {
    const cv = ref.current
    if (!cv) return
    const g = cv.getContext('2d')
    if (!g) return
    const W = cv.width, H = cv.height
    const spawn = () => sim.current.targets.push({
      x: 30 + Math.random() * (W - 60), y: 30 + Math.random() * (H - 60),
      r: 14 + Math.random() * 12, born: performance.now(),
    })
    spawn()
    let raf = 0
    const loop = () => {
      const now = performance.now()
      sim.current.targets = sim.current.targets.filter(t => now - t.born < 4000)
      if (sim.current.targets.length === 0) spawn()
      g.fillStyle = 'rgba(0,0,0,0.28)'
      g.fillRect(0, 0, W, H)
      // 轨迹（2s 淡出）——体感移动是否流畅、有没有跳变，一眼可见
      sim.current.trail = sim.current.trail.filter(p => now - p.t < 2000)
      g.strokeStyle = 'rgba(34,211,238,0.5)'
      g.beginPath()
      sim.current.trail.forEach((p, i) => (i ? g.lineTo(p.x, p.y) : g.moveTo(p.x, p.y)))
      g.stroke()
      sim.current.targets.forEach(t => {
        const age = (now - t.born) / 4000
        g.strokeStyle = `rgba(251,191,36,${1 - age * 0.6})`
        g.beginPath(); g.arc(t.x, t.y, t.r, 0, 7); g.stroke()
        g.fillStyle = `rgba(251,191,36,${0.25 - age * 0.2})`
        g.fill()
      })
      g.fillStyle = '#67e8f9'
      g.beginPath(); g.arc(sim.current.mx, sim.current.my, 3, 0, 7); g.fill()
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [])
  const track = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    const p = { x: e.clientX - r.left, y: e.clientY - r.top, t: performance.now() }
    sim.current.mx = p.x; sim.current.my = p.y
    sim.current.trail.push(p)
    if (sim.current.trail.length > 400) sim.current.trail.shift()
  }
  const shoot = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    const x = e.clientX - r.left, y = e.clientY - r.top
    setShots(s => s + 1)
    if (sim.current.targets.some(t => (x - t.x) ** 2 + (y - t.y) ** 2 <= t.r ** 2)) {
      setScore(s => s + 1)
      sim.current.targets = sim.current.targets.filter(t => (x - t.x) ** 2 + (y - t.y) ** 2 > t.r ** 2)
    }
  }
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-3 text-[10px] text-text-low">
        <span>用体感/摇杆映射出的鼠标来瞄准打靶（先在体验区开启体感瞄准或摇杆→鼠标）</span>
        <span className="text-accent">命中 {score}</span>
        <span>/ 开枪 {shots}</span>
      </div>
      <canvas ref={ref} width={560} height={200}
        className="w-full cursor-crosshair rounded border border-border-soft"
        onMouseMove={track} onClick={shoot} />
    </div>
  )
}

// 键盘场：按键计数 + 频率——测固件连发（键表→键盘）、宏、摇杆转键盘
function KeyRange() {
  const [keys, setKeys] = useState<Record<string, { count: number; ts: number[]; down: boolean }>>({})
  useEffect(() => {
    const hit = (ev: KeyboardEvent, down: boolean) => {
      if (down && ev.repeat) return                 // 系统自动重复不算，只数真实按下
      const k = ev.key === ' ' ? 'Space' : ev.key
      setKeys(cur => {
        const e = cur[k] ?? { count: 0, ts: [], down: false }
        return { ...cur, [k]: down
          ? { count: e.count + 1, ts: [...e.ts.slice(-40), performance.now()], down: true }
          : { ...e, down: false } }
      })
    }
    const dn = (e: KeyboardEvent) => hit(e, true)
    const up = (e: KeyboardEvent) => hit(e, false)
    window.addEventListener('keydown', dn)
    window.addEventListener('keyup', up)
    return () => { window.removeEventListener('keydown', dn); window.removeEventListener('keyup', up) }
  }, [])
  const rows = Object.entries(keys).filter(([, e]) => e.count > 0).slice(-8)
  return (
    <div className="space-y-1">
      <div className="text-[10px] text-text-low">
        手柄键映射成键盘（体验区 → 连发 Turbo / 摇杆→键盘 / 宏）后在这里按——次数和实时频率一眼可见，连发是否生效立刻知道
      </div>
      <div className="flex flex-wrap gap-1.5">
        {rows.length === 0 && <span className="text-[11px] text-text-low">（在这个窗口里按键开始计数）</span>}
        {rows.map(([k, e]) => {
          const recent = e.ts.filter(t => performance.now() - t < 2000).length
          return (
            <span key={k} className={`rounded border px-2 py-1 text-[11px] ${e.down ? 'border-accent/60 bg-accent/10 text-accent' : 'border-border-soft text-text-mid'}`}>
              {k} × {e.count}{recent >= 2 ? ` · ${(recent / 2).toFixed(1)}/s` : ''}
            </span>
          )
        })}
      </div>
    </div>
  )
}

export function GameSimPanel() {
  const [st, setSt] = useState<any>(null)
  const [msg, flash] = useFlash()
  const load = useCallback(() => { api.expSim().then(setSt).catch(e => flash('', e)) }, [])
  useEffect(() => {
    load()
    const t = setInterval(load, 1500)
    return () => clearInterval(t)
  }, [load])
  if (!st) return <div className="space-y-2"><NoDev /><Err e={msg} /></div>
  const run = (s: string) =>
    api.expSimRun(s).then((r: any) => { setSt(r); flash(`▶ ${r.scenarios?.[s] ?? s}`) }).catch(e => flash('', e))
  const btn = (s: string, label: string, cls = BTN) => (
    <button className={cls} onClick={() => run(s)}>{label}</button>
  )
  return (
    <div className="space-y-2.5">
      <div className="flex flex-wrap items-center gap-2 text-[10px] text-text-low">
        <span>{st.running ? <b className="text-accent">运行中：{st.scenarios?.[st.running] ?? st.running}</b> : '空闲'}</span>
        <span>· DSX 包 {st.stats?.dsx_sent ?? 0}</span>
        <span>· RGB 包 {st.stats?.rgb_sent ?? 0}</span>
        <span>· 场次 {st.stats?.runs ?? 0}</span>
      </div>
      <Row label="扳机场">
        {btn('shooting', '射击 6s')}
        {btn('explosion', '爆炸')}
        {btn('race', '赛车 8s')}
        {btn('idle', '松开复位')}
      </Row>
      <Row label="灯场">
        {btn('lowhp', '低血量（红）')}
        {btn('heal', '回血（绿）')}
        {btn('idle', '熄灯')}
        <span className="text-[10px] text-text-low">需先启动「Mod 灯效桥」——RGB 走真实桥链路</span>
      </Row>
      {st.stats?.note && <Err e={st.stats.note} />}
      <div className="rounded-md border border-border-soft p-2">
        <div className="mb-1 text-[10px] text-text-low">靶场 · 体感瞄准 / 摇杆→鼠标 闭环验证</div>
        <AimRange />
      </div>
      <div className="rounded-md border border-border-soft p-2">
        <div className="mb-1 text-[10px] text-text-low">键盘场 · 连发 / 宏 / 摇杆→键盘 闭环验证</div>
        <KeyRange />
      </div>
      <div className="text-[10px] text-text-low">
        扳机/灯事件与真游戏 Mod 同一条 UDP 链路（DSX 协议→ingress→cmd51；RGB→桥→灯表），这里通了真游戏就通。
      </div>
      <Err e={msg} />
    </div>
  )
}

// ==================== #17 体感弹珠迷宫 ====================
// 手柄倾斜 → 弹珠。物理在前端跑（60fps 顺滑），倾斜由后端 0xEF 运动流解算，
// 40ms 轮询。面板同时是「手柄有没有真体感」的答案器：原始加速度/陀螺/数据源可见。

const MAZE_W = 560, MAZE_H = 360, BALL_R = 7
// 迷宫布局：外墙 + 内墙 (x,y,w,h)，3 个洞 + 右下角终点
const MAZE_WALLS: Array<[number, number, number, number]> = [
  [0, 0, MAZE_W, 8], [0, MAZE_H - 8, MAZE_W, 8], [0, 0, 8, MAZE_H], [MAZE_W - 8, 0, 8, MAZE_H],
  [90, 8, 8, 220], [180, 130, 8, 222], [270, 8, 8, 220], [360, 130, 8, 222], [450, 8, 8, 220],
  [90, 220, 200, 8], [270, 228, 8, 60],
]
const MAZE_HOLES = [
  { x: 135, y: 115, r: 13 }, { x: 315, y: 240, r: 13 }, { x: 405, y: 70, r: 13 },
]
const MAZE_GOAL = { x: 495, y: 300, w: 56, h: 50 }
const START = { x: 40, y: 40 }

function MazeBoard({ onTelemetry, invX, invY }: { onTelemetry: (t: any) => void; invX: boolean; invY: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const state = useRef({
    x: START.x, y: START.y, vx: 0, vy: 0,
    tilt: [0, 0] as [number, number],
    falls: 0, wins: 0, flash: '', flashT: 0,
    falling: 0,                    // >0 = 掉洞动画中（时间戳）
  })
  useEffect(() => {
    const cv = ref.current
    if (!cv) return
    const g = cv.getContext('2d')
    if (!g) return
    let raf = 0
    let last = performance.now()
    const poll = setInterval(() => {
      api.expMaze().then((r: any) => {
        if (r?.tilt) state.current.tilt = r.tilt
        if (r) onTelemetry(r)
      }).catch(() => { })
    }, 40)
    const reset = () => {
      const s = state.current
      s.x = START.x; s.y = START.y; s.vx = 0; s.vy = 0; s.falling = 0
    }
    const loop = () => {
      const now = performance.now()
      const dt = Math.min(0.05, (now - last) / 1000)
      last = now
      const s = state.current
      if (s.falling) {
        if (now - s.falling > 600) reset()
      } else {
        let [tx, ty] = s.tilt
        if (invX) tx = -tx
        if (invY) ty = -ty
        s.vx += tx * 1600 * dt
        s.vy += ty * 1600 * dt
        s.vx *= 0.995; s.vy *= 0.995
        s.x += s.vx * dt; s.y += s.vy * dt
        // 墙碰撞（圆 vs AABB，沿最浅轴弹出反弹）
        for (const [wx, wy, ww, wh] of MAZE_WALLS) {
          const cx = Math.max(wx, Math.min(s.x, wx + ww))
          const cy = Math.max(wy, Math.min(s.y, wy + wh))
          const dx = s.x - cx, dy = s.y - cy
          const d2 = dx * dx + dy * dy
          if (d2 < BALL_R * BALL_R) {
            const d = Math.sqrt(d2) || 0.001
            const nx = dx / d, ny = dy / d
            s.x = cx + nx * BALL_R; s.y = cy + ny * BALL_R
            const dot = s.vx * nx + s.vy * ny
            s.vx -= 1.6 * dot * nx; s.vy -= 1.6 * dot * ny
          }
        }
        // 掉洞
        for (const h of MAZE_HOLES) {
          if ((s.x - h.x) ** 2 + (s.y - h.y) ** 2 < (h.r - 2) ** 2) {
            s.falling = now; s.falls++; s.flash = '掉洞了！'; s.flashT = now
            break
          }
        }
        // 终点
        if (s.x > MAZE_GOAL.x && s.x < MAZE_GOAL.x + MAZE_GOAL.w &&
            s.y > MAZE_GOAL.y && s.y < MAZE_GOAL.y + MAZE_GOAL.h) {
          s.wins++; s.flash = '到达终点！'; s.flashT = now; reset()
        }
      }
      // 绘制
      g.fillStyle = '#101018'
      g.fillRect(0, 0, MAZE_W, MAZE_H)
      g.fillStyle = '#2a2a3a'
      for (const [wx, wy, ww, wh] of MAZE_WALLS) g.fillRect(wx, wy, ww, wh)
      for (const h of MAZE_HOLES) {
        g.fillStyle = '#000'
        g.beginPath(); g.arc(h.x, h.y, h.r, 0, 7); g.fill()
        g.strokeStyle = '#444'; g.stroke()
      }
      g.fillStyle = 'rgba(52,211,153,0.45)'
      g.fillRect(MAZE_GOAL.x, MAZE_GOAL.y, MAZE_GOAL.w, MAZE_GOAL.h)
      g.fillStyle = '#34d399'
      g.font = '10px sans-serif'; g.fillText('终点', MAZE_GOAL.x + 16, MAZE_GOAL.y + 28)
      // 弹珠（掉洞时缩小消失）
      const scale = s.falling ? Math.max(0, 1 - (now - s.falling) / 500) : 1
      g.fillStyle = '#67e8f9'
      g.beginPath(); g.arc(s.x, s.y, BALL_R * scale, 0, 7); g.fill()
      if (s.flash && now - s.flashT < 1500) {
        g.fillStyle = '#fbbf24'; g.font = 'bold 18px sans-serif'
        g.fillText(s.flash, MAZE_W / 2 - 50, 30)
      }
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => { cancelAnimationFrame(raf); clearInterval(poll) }
  }, [onTelemetry, invX, invY])
  return (
    <div className="space-y-1">
      <canvas ref={ref} width={MAZE_W} height={MAZE_H} className="w-full rounded border border-border-soft" />
      <MazeHud state={state} />
    </div>
  )
}

function MazeHud({ state }: { state: React.MutableRefObject<any> }) {
  const [, force] = useState(0)
  useEffect(() => { const t = setInterval(() => force(n => n + 1), 500); return () => clearInterval(t) }, [])
  const s = state.current
  return (
    <div className="text-[10px] text-text-low">
      到达 {s.wins} 次 · 掉洞 {s.falls} 次
      <button className={BTN + ' ml-2'} onClick={() => { s.wins = 0; s.falls = 0 }}>清零</button>
    </div>
  )
}

export function MazePanel() {
  const [tel, setTel] = useState<any>(null)
  const [msg, flash] = useFlash()
  const [inv, setInv] = useState(() => {
    try { return JSON.parse(localStorage.getItem('maze_inv') ?? '{"x":false,"y":false}') }
    catch { return { x: false, y: false } }
  })
  useEffect(() => { localStorage.setItem('maze_inv', JSON.stringify(inv)) }, [inv])
  // 反转在物理层生效（MazeBoard 读 tilt 时取反），存 localStorage 记住偏好
  const toggleInv = (k: 'x' | 'y') => setInv((c: any) => ({ ...c, [k]: !c[k] }))
  const imuOk = tel?.has_imu
  return (
    <div className="space-y-2.5">
      {/* 自检：回答「手柄到底有没有真体感」 */}
      <div className={`rounded-md border p-2 text-[11px] ${imuOk ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300' : 'border-red-500/40 bg-red-500/10 text-red-300'}`}>
        {tel === null ? '自检中…' : imuOk ? (
          <>
            ✓ 检测到体感数据流（{tel.source === 'gyro_fallback' ? '陀螺仪模式：固件未填加速度，用陀螺积分' : '加速度计+陀螺仪'}）
            <span className="ml-2 text-text-low">帧 {tel.frames} ｜ 加速度模长 {tel.accel_mag} ｜ 陀螺 ({tel.raw_gyro.join(', ')})</span>
          </>
        ) : (
          <>✗ 没有任何体感数据（加速度模长 {tel.accel_mag}，陀螺全 0）——当前模式下固件没输出运动数据，试试重启手柄或连 Switch 模式验证硬件</>
        )}
      </div>
      {/* 实时倾斜条：不用玩迷宫，放平→倾斜立刻能验证方向与增益是否对称 */}
      <div className="rounded-md border border-border-soft p-2">
        <div className="mb-1 flex items-center gap-2 text-[10px] text-text-low">
          实时倾斜
          <span className={tel?.autocal ? 'text-emerald-300' : 'text-amber-300'}>
            {tel?.autocal
              ? '锚点已锁定（软件不会再动它）'
              : tel?.anchor === 'flat' ? '平放静止中，正在锚定平地…' : '把手柄平放静止 1 秒以锚定平地'}
          </span>
          <span className="ml-2">
            {tel?.anchor === 'held' ? '（非平放：锚点保持不动）' : tel?.anchor === 'moving' ? '（运动中）' : ''}
          </span>
        </div>
        {(['x', 'y'] as const).map(k => {
          const v = Math.max(-1, Math.min(1, tel?.tilt?.[k === 'x' ? 0 : 1] ?? 0))
          return (
            <div key={k} className="mb-1 flex items-center gap-2 text-[10px] text-text-low">
              <span className="w-10">{k === 'x' ? '左右' : '前后'}</span>
              <div className="relative h-2 flex-1 rounded bg-white/10">
                <div className="absolute left-1/2 top-0 h-full w-px bg-white/30" />
                <div className={`absolute top-0 h-full rounded ${v >= 0 ? 'bg-cyan-400' : 'bg-amber-400'}`}
                  style={v >= 0
                    ? { left: '50%', width: `${v * 50}%` }
                    : { left: `${50 + v * 50}%`, width: `${-v * 50}%` }} />
              </div>
              <span className="w-14 text-right">{k === 'x' ? (v > 0.05 ? '偏右' : v < -0.05 ? '偏左' : '居中') : (v > 0.05 ? '偏后(向下滚)' : v < -0.05 ? '偏前(向上滚)' : '居中')}</span>
            </div>
          )
        })}
      </div>
      <Row label="校准">
        <button className={BTN_ACC} disabled={!imuOk || tel?.source === 'gyro_fallback'}
          onClick={() => api.expMazeCal().then(() => flash('✓ 锚点已重设为当前姿态')).catch(e => flash('', e))}>
          重设锚点为当前姿态
        </button>
        <span className="text-[10px] text-text-low">锚点只在第一次平放静止时自动采一次，之后软件不会再动它；只有你在这里手动点才会重设</span>
      </Row>
      <Row label="方向">
        <button className={inv.x ? BTN_ACC : BTN} onClick={() => toggleInv('x')}>左右 {inv.x ? '（已反转）' : '正常'}</button>
        <button className={inv.y ? BTN_ACC : BTN} onClick={() => toggleInv('y')}>前后 {inv.y ? '（已反转）' : '正常'}</button>
        <span className="text-[10px] text-text-low">滚反了点一下就正（记住偏好）</span>
      </Row>
      <MazeBoard onTelemetry={setTel} invX={inv.x} invY={inv.y} />
      <Err e={msg} />
    </div>
  )
}

// ==================== 注册表：feature id → 面板 ====================
export const PANELS: Record<string, React.FC> = {
  gyro: Safe(GyroPanel),
  turbo: Safe(TurboPanel),
  stickcfg: Safe(StickCfgPanel),
  devcfg: Safe(DevCfgPanel),
  arbitration: Safe(ArbitrationPanel),
  gyrofw: Safe(GyroFwPanel),
  stickmap: Safe(StickMapPanel),
  rgbbridge: Safe(RgbBridgePanel),
  diagnostics: Safe(DiagnosticsPanel),
  slots: Safe(SlotsPanel),
  sharecode: Safe(ShareCodePanel),
  switchbank: Safe(SwitchBankPanel),
  gripvib: Safe(GripVibPanel),
  screenplus: Safe(ScreenPlusPanel),
  factoryreset: Safe(FactoryResetPanel),
  gamesim: Safe(GameSimPanel),
  maze: Safe(MazePanel),
}
