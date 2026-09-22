// 实时手柄卡（原手柄测试页，2026-09-22 并入总览）：交互式手柄示意图——物理按压/摇杆/
// 扳机实时映射到图上对应位置。数据源：Gamepad API（标准输入接口）+ 后端 0xEF 拓展键事件。
import { useEffect, useMemo, useState } from 'react'
import { Gamepad, Keyboard, Radio } from 'lucide-react'
import { api, type EngineEvent } from '../api'

interface PadSnap {
  id: string
  axes: number[]
  buttons: { pressed: boolean; value: number }[]
}

function useGamepad() {
  const [pad, setPad] = useState<PadSnap | null>(null)
  useEffect(() => {
    let raf = 0
    const tick = () => {
      const raw = Array.from(navigator.getGamepads?.() ?? []).find((g) => g)
      if (raw) {
        setPad({
          id: raw.id,
          axes: [...raw.axes],
          buttons: raw.buttons.map((b) => ({ pressed: b.pressed, value: b.value })),
        })
      } else {
        setPad(null)
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [])
  return pad
}

// ---- SVG 部件：亮 = 实际按压 ----
const ON_FILL = 'rgba(34,211,239,.92)'
const OFF_FILL = '#1a1a2c'
const ON_STROKE = '#22d3ee'
const OFF_STROKE_SOLID = '#34345a'

function Dot({ cx, cy, r, label, on, title, dashed }: {
  cx: number; cy: number; r: number; label: string; on: boolean; title?: string; dashed?: boolean
}) {
  return (
    <g>
      {title && <title>{title}</title>}
      <circle cx={cx} cy={cy} r={r}
        fill={on ? ON_FILL : OFF_FILL}
        stroke={on ? ON_STROKE : OFF_STROKE_SOLID}
        strokeWidth={1.5}
        strokeDasharray={dashed ? '4 3' : undefined}
        style={{ filter: on ? 'drop-shadow(0 0 7px rgba(34,211,239,.55))' : undefined, transition: 'fill 40ms, filter 40ms' }} />
      <text x={cx} y={cy + 3.5} textAnchor="middle" fontSize={r >= 15 ? 12 : 10} fontWeight={600}
        fill={on ? '#062730' : '#8b8ba7'}>{label}</text>
    </g>
  )
}

function Bumper({ x, w, label, on }: { x: number; w: number; label: string; on: boolean }) {
  return (
    <g>
      <title>{label}</title>
      <rect x={x} y={104} width={w} height={30} rx={15}
        fill={on ? ON_FILL : OFF_FILL} stroke={on ? ON_STROKE : OFF_STROKE_SOLID} strokeWidth={1.5}
        style={{ filter: on ? 'drop-shadow(0 0 7px rgba(34,211,239,.55))' : undefined, transition: 'fill 40ms' }} />
      <text x={x + w / 2} y={123} textAnchor="middle" fontSize={12} fontWeight={600}
        fill={on ? '#062730' : '#8b8ba7'}>{label}</text>
    </g>
  )
}

/** 扳机：左上/右上竖条，模拟量以填充高度呈现（outline 里液面升降） */
function TriggerBar({ x, label, v }: { x: number; label: string; v: number }) {
  const H = 46, W = 26
  const fh = Math.max(0, Math.min(1, v)) * (H - 6)
  return (
    <g>
      <title>{`${label} ${(v * 100).toFixed(0)}%`}</title>
      <rect x={x} y={50} width={W} height={H} rx={13} fill="#141422" stroke={v > 0.02 ? ON_STROKE : OFF_STROKE_SOLID} strokeWidth={1.5} />
      <rect x={x + 3} y={50 + 3 + (H - 6) - fh} width={W - 6} height={fh} rx={10} fill={ON_FILL} opacity={0.85} />
      <text x={x + W / 2} y={44} textAnchor="middle" fontSize={11} fontWeight={600} fill="#8b8ba7">{label}</text>
    </g>
  )
}

function StickSvg({ cx, cy, x, y, press, title }: {
  cx: number; cy: number; x: number; y: number; press: boolean; title: string
}) {
  const kx = cx + Math.max(-1, Math.min(1, x)) * 14
  const ky = cy + Math.max(-1, Math.min(1, y)) * 14
  return (
    <g>
      <title>{title}</title>
      <circle cx={cx} cy={cy} r={34} fill="#141422" stroke={press ? ON_STROKE : OFF_STROKE_SOLID} strokeWidth={press ? 2 : 1.5}
        style={{ filter: press ? 'drop-shadow(0 0 8px rgba(34,211,239,.5))' : undefined }} />
      <circle cx={kx} cy={ky} r={20} fill={press ? ON_FILL : '#23233a'} stroke={press ? ON_STROKE : '#3a3a5c'} strokeWidth={1.5}
        style={{ transition: 'fill 40ms' }} />
      {press && <text x={cx} y={cy + 72} textAnchor="middle" fontSize={10} fill={ON_STROKE} fontWeight={600}>按下</text>}
    </g>
  )
}

/** 十字键：四片圆角矩形 */
function Dpad({ cx, cy, on }: { cx: number; cy: number; on: (i: number) => boolean }) {
  const arm = (px: number, py: number, w: number, h: number, i: number, label: string, lx: number, ly: number) => (
    <g key={i}>
      <rect x={px} y={py} width={w} height={h} rx={7}
        fill={on(i) ? ON_FILL : OFF_FILL} stroke={on(i) ? ON_STROKE : OFF_STROKE_SOLID} strokeWidth={1.5}
        style={{ filter: on(i) ? 'drop-shadow(0 0 7px rgba(34,211,239,.55))' : undefined, transition: 'fill 40ms' }} />
      <text x={lx} y={ly} textAnchor="middle" fontSize={12} fontWeight={700} fill={on(i) ? '#062730' : '#8b8ba7'}>{label}</text>
    </g>
  )
  return (
    <g>
      {arm(cx - 13, cy - 46, 26, 40, 12, '▲', cx, cy - 26)}   {/* 上 */}
      {arm(cx - 13, cy + 6, 26, 40, 13, '▼', cx, cy + 33)}    {/* 下 */}
      {arm(cx - 46, cy - 13, 40, 26, 14, '◀', cx - 26, cy + 4)} {/* 左 */}
      {arm(cx + 6, cy - 13, 40, 26, 15, '▶', cx + 26, cy + 4)}  {/* 右 */}
    </g>
  )
}

/** 手柄示意图：按键位置 = 实际按键（标准 Gamepad 映射 + 0xEF 拓展键） */
function PadDiagram({ pad, extNow }: { pad: PadSnap | null; extNow: Set<string> }) {
  const btn = (i: number) => pad?.buttons[i]?.pressed ?? false
  const ax = (i: number) => pad?.axes[i] ?? 0
  return (
    <div className="relative flex items-center justify-center overflow-hidden rounded-xl border border-border-soft bg-[#0a0a12] p-2">
      <div className="pointer-events-none absolute inset-0"
        style={{ background: 'radial-gradient(ellipse 75% 70% at 50% 45%, rgba(34,211,239,.05), transparent 70%)' }} />
      <svg viewBox="0 0 640 400" className="relative w-full max-w-2xl">
        {/* 机身 */}
        <g fill="#12121c" stroke="#2a2a44" strokeWidth={2}>
          <ellipse cx={150} cy={262} rx={82} ry={96} />
          <ellipse cx={490} cy={262} rx={82} ry={96} />
          <rect x={140} y={132} width={360} height={128} rx={64} />
        </g>

        {/* 头部拓展键 LM / RM（顶部两颗） */}
        <Dot cx={268} cy={142} r={11} label="LM" on={extNow.has('lm')} title="LM（头部左）" />
        <Dot cx={372} cy={142} r={11} label="RM" on={extNow.has('rm')} title="RM（头部右）" />

        {/* LOGO / 视图 / 菜单 */}
        <Dot cx={320} cy={170} r={16} label="⌂" on={btn(16)} title="LOGO" />
        <Dot cx={293} cy={206} r={13} label="⧉" on={btn(8)} title="视图" />
        <Dot cx={347} cy={206} r={13} label="☰" on={btn(9)} title="菜单" />

        {/* 左摇杆（推动方向实时映射） */}
        <StickSvg cx={185} cy={212} x={ax(0)} y={ax(1)} press={btn(10)} title="左摇杆（L3 按下高亮）" />
        {/* 十字键 */}
        <Dpad cx={185} cy={318} on={btn} />

        {/* 右摇杆 */}
        <StickSvg cx={395} cy={318} x={ax(2)} y={ax(3)} press={btn(11)} title="右摇杆（R3 按下高亮）" />

        {/* 面键 ABXY（Xbox 布局：Y上 A下 X左 B右） */}
        <Dot cx={455} cy={158} r={17} label="Y" on={btn(3)} title="Y / 三角" />
        <Dot cx={455} cy={242} r={17} label="A" on={btn(0)} title="A / 交叉" />
        <Dot cx={413} cy={200} r={17} label="X" on={btn(2)} title="X / 方块" />
        <Dot cx={497} cy={200} r={17} label="B" on={btn(1)} title="B / 圆圈" />

        {/* 肩键 */}
        <Bumper x={108} w={128} label="LB" on={btn(4)} />
        <Bumper x={404} w={128} label="RB" on={btn(5)} />
        {/* 扳机（模拟量） */}
        <TriggerBar x={158} label="LT" v={pad?.buttons[6]?.value ?? 0} />
        <TriggerBar x={456} label="RT" v={pad?.buttons[7]?.value ?? 0} />

        {/* 背部拓展键 M1-M4（虚线 = 位于背面，按压照样亮） */}
        <Dot cx={100} cy={262} r={13} label="M2" on={extNow.has('m2')} title="M2（背左上）" dashed />
        <Dot cx={132} cy={330} r={13} label="M4" on={extNow.has('m4')} title="M4（背左下）" dashed />
        <Dot cx={540} cy={262} r={13} label="M1" on={extNow.has('m1')} title="M1（背右上）" dashed />
        <Dot cx={508} cy={330} r={13} label="M3" on={extNow.has('m3')} title="M3（背右下）" dashed />
      </svg>
    </div>
  )
}

// 拓展键六颗（ADR-019）：id=0xEF 键位图事件里的键名
const EXT_CHIP = [
  { key: 'LM', id: 'lm', pos: '头左' },
  { key: 'RM', id: 'rm', pos: '头右' },
  { key: 'M1', id: 'm1', pos: '背右上' },
  { key: 'M2', id: 'm2', pos: '背左上' },
  { key: 'M3', id: 'm3', pos: '背右下' },
  { key: 'M4', id: 'm4', pos: '背左下' },
]

/** 总览页「实时手柄」卡：示意图 + 拓展键 + 特殊键监听 + 校准浮层（嵌入用） */
export default function PadLiveCard({ events }: { events: EngineEvent[] }) {
  const pad = useGamepad()

  // 特殊键：后端两条监听通道的最新事件
  const hidkeys = useMemo(() => events.filter(e => e.kind === 'hidkey').slice(-8).reverse(), [events])
  const rawhids = useMemo(() => events.filter(e => e.kind === 'rawhid').slice(-8).reverse(), [events])
  const lastKeys: string[] = (hidkeys[0]?.keys as string[]) ?? []

  // 拓展键（ADR-019）：0xEF 物理键位图直读——映射前的真实按压，与老按键天然区分
  const extKeysNow = useMemo(
    () => new Set((events.filter(e => e.kind === 'extkey').slice(-1)[0]?.keys as string[]) ?? []),
    [events])
  // 拓展键监听开关（ADR-028 修订 2）：0xEF 流默认关（手柄才能休眠），打开监听才
  // 拉起——立即请求 + 15s 心跳保活；关闭/离开页面即退订，30s 后自动收流
  const [listening, setListening] = useState(false)
  useEffect(() => {
    if (!listening) return
    api.rawStream(true).catch(() => {})
    const hb = setInterval(() => api.rawStream(true).catch(() => {}), 15000)
    return () => { clearInterval(hb); api.rawStream(false).catch(() => {}) }
  }, [listening])
  const extNowLive = useMemo(() => (listening ? extKeysNow : new Set<string>()), [listening, extKeysNow])
  const [keyMap, setKeyMap] = useState<Array<{ name: string; target_name: string }> | null>(null)
  useEffect(() => { api.extKeys().then(m => { if (m.ok) setKeyMap(m.keys) }).catch(() => {}) }, [])

  // 受控键位校准（ADR-016）：跟随 attrib 事件展示引导浮层
  const [attrib, setAttrib] = useState<{ phase: string; key?: string; mapping?: Record<string, string>; missing?: string[] } | null>(null)
  const attribEvts = useMemo(() => events.filter(e => e.kind === 'attrib'), [events])
  useEffect(() => {
    const e = attribEvts[attribEvts.length - 1]
    if (e) setAttrib({ phase: e.phase as string, key: e.key as string | undefined, mapping: e.mapping as Record<string, string> | undefined, missing: e.missing as string[] | undefined })
  }, [attribEvts.length])  // eslint-disable-line react-hooks/exhaustive-deps

  const f2 = (v: number) => v.toFixed(2)

  return (
    <div className="space-y-4">
      <div className="card p-4">
        <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1">
          <div className="flex items-center gap-2 text-[12px] text-text-mid">
            <Gamepad size={14} className="text-accent" /> 实时手柄
          </div>
          {/* 拓展键监听开关：默认关（流关着，手柄可休眠） */}
          <button
            className={`rounded-md border px-2 py-0.5 text-[11px] transition-colors ${
              listening
                ? 'border-accent/50 bg-accent/15 text-accent'
                : 'border-border-soft text-text-low hover:text-text-mid'}`}
            onClick={() => setListening(v => !v)}
            title={listening ? '监听中：手柄监听期间不会自动休眠' : '打开后才能看到拓展键按压（监听期间手柄不休眠）'}>
            {listening ? '拓展键监听中' : '拓展键监听关'}
          </button>
          {/* 拓展键迷你章 */}
          <div className="flex gap-1.5">
            {EXT_CHIP.map(({ key, id }) => {
              const on = extNowLive.has(id)
              return (
                <span key={id} className={`rounded px-1.5 py-0.5 font-mono text-[10px] transition-all ${
                  on ? 'bg-accent/20 text-accent shadow-[0_0_10px_rgba(34,211,238,.35)]' : 'bg-white/5 text-text-low'}`}>
                  {key}
                </span>
              )
            })}
          </div>
          <div className="ml-auto truncate font-mono text-[11px] text-text-low">
            {pad ? pad.id : '未检测到游戏控制器——手柄开机/重插一次'}
          </div>
        </div>
        <PadDiagram pad={pad} extNow={extNowLive} />
        {/* 数值读数：示意图之外的精确值 */}
        <div className="mt-3 grid grid-cols-2 gap-3 font-mono text-[11px] text-text-low md:grid-cols-4">
          <div>左摇杆 <span className="text-accent">{f2(pad?.axes[0] ?? 0)}, {f2(pad?.axes[1] ?? 0)}</span></div>
          <div>右摇杆 <span className="text-accent">{f2(pad?.axes[2] ?? 0)}, {f2(pad?.axes[3] ?? 0)}</span></div>
          <div>LT <span className="text-accent">{((pad?.buttons[6]?.value ?? 0) * 100).toFixed(0)}%</span></div>
          <div>RT <span className="text-accent">{((pad?.buttons[7]?.value ?? 0) * 100).toFixed(0)}%</span></div>
        </div>
        {keyMap && (
          <div className="mt-2 font-mono text-[11px] text-text-low">
            拓展键固件映射：{keyMap.map(k => `${k.name.toUpperCase()}→${k.target_name}`).join('  ')}
          </div>
        )}
      </div>

      {/* 特殊键监听 */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="card p-4">
          <div className="mb-3 flex items-center gap-2 text-[12px] text-text-mid">
            <Keyboard size={14} className="text-accent" /> 键盘接口
          </div>
          <div className="mb-3 flex min-h-8 flex-wrap gap-1.5">
            {lastKeys.length
              ? lastKeys.map(k => <span key={k} className="tag border-accent/50 !text-accent">{k}</span>)
              : <span className="text-[12px] text-text-low">按下背键 / 扩展键试试…</span>}
          </div>
          <div className="space-y-0.5 font-mono text-[11px] text-text-low">
            {hidkeys.map((e, i) => (
              <div key={i} className="truncate">{e.ts}  {(e.keys as string[])?.join('+') || '—'}  <span className="text-text-low/60">{e.raw as string}</span></div>
            ))}
          </div>
        </div>
        <div className="card p-4">
          <div className="mb-3 flex items-center gap-2 text-[12px] text-text-mid">
            <Radio size={14} className="text-accent" /> vendor 接口非协议帧
          </div>
          <div className="space-y-0.5 font-mono text-[11px] text-text-low">
            {rawhids.length
              ? rawhids.map((e, i) => <div key={i} className="truncate">{e.ts}  {e.hex as string}</div>)
              : <span className="text-[12px] text-text-low">暂无原始帧</span>}
          </div>
        </div>
      </div>

      {/* 校准引导浮层 */}
      {attrib && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm">
          <div className="card w-[420px] p-8 text-center">
            {attrib.phase === 'prompt' && (
              <>
                <div className="mb-2 text-[12px] text-text-mid">准备——下一步请按住</div>
                <div className="font-mono text-6xl font-bold text-accent">{attrib.key}</div>
              </>
            )}
            {attrib.phase === 'window' && (
              <>
                <div className="mb-2 text-[12px] text-text-mid">现在按住不放</div>
                <div className="font-mono text-6xl font-bold text-accent shadow-[0_0_32px_rgba(34,211,238,.5)]">{attrib.key}</div>
                <div className="mt-4 text-[12px] text-text-low">持续按住并松开几次（5 秒采集窗口）…</div>
              </>
            )}
            {(attrib.phase === 'done' || attrib.phase === 'error') && (
              <>
                <div className="mb-3 text-[13px] text-text-mid">
                  {attrib.phase === 'done' ? '校准完成' : '校准出错'}
                </div>
                {attrib.phase === 'done' && (
                  <div className="space-y-2 font-mono text-[12px]">
                    {Object.entries(attrib.mapping ?? {}).map(([raw, name]) => (
                      <div key={raw} className="flex justify-between text-accent"><span>{name}</span><span className="text-text-low">{raw}</span></div>
                    ))}
                    {(attrib.missing ?? []).map(k => (
                      <div key={k} className="flex justify-between text-text-low/60"><span>{k}</span><span>无输出（静默）</span></div>
                    ))}
                    {(attrib.missing ?? []).some(k => k.startsWith('M')) && (
                      <div className="pt-2 text-left text-[11px] leading-relaxed text-text-low">
                        背键静默 = 固件默认无映射，需设备端 0xA3 映射写入后才有输出（ADR-016）。
                      </div>
                    )}
                  </div>
                )}
                <button className="btn mt-5 justify-center" onClick={() => setAttrib(null)}>关闭</button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
