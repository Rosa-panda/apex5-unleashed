// #4 设备设置页（ADR-029 F2 自 panels.tsx 逐字搬出）
import { useCallback, useEffect, useState } from 'react'
import { api } from '../../../api'
import { BTN, BTN_DANGER, Err, NoDev, Row, useFlash } from '../ui'

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
