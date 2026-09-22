// #3 曲线编辑器（ADR-029 F2 自 panels.tsx 逐字搬出）
import { useCallback, useEffect, useState } from 'react'
import { api } from '../../../api'
import { BTN, BTN_ACC, CurveCanvas, Err, NoDev, Row, useFlash } from '../ui'

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
