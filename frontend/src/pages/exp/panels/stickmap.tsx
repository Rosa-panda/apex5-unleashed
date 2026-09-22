// #7 摇杆→鼠标/键盘（ADR-029 F2 自 panels.tsx 逐字搬出）
import { useCallback, useEffect, useState } from 'react'
import { api } from '../../../api'
import { BTN, BTN_ACC, Err, NoDev, Row, useFlash } from '../ui'

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
