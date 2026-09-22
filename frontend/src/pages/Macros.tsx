// 宏页（ADR-021 v3.1 方案）：板载宏存在 profile blob 的宏页里（163/164/165 一次连宏带绑定写入）。
// 执行在固件：写完关软件也生效。宏没有名字字段，以触发键为身份；上限 5 条 / 全页 128 步 / 10ms 精度。
import { useEffect, useRef, useState } from 'react'
import { Circle, CircleStop, Copy, Download, Pencil, Play, RotateCcw, Save, Trash2, Upload, Wand2 } from 'lucide-react'
import { api, type EngineEvent, type Macro } from '../api'
import { DeviceGate } from '../Offline'

// 0xEF 位图 32 键全名（与后端 protocol.KEY32_NAMES 同源）
const KEY_NAMES: Record<number, string> = {
  0: '十字上', 1: '十字右', 2: '十字下', 3: '十字左', 4: 'A', 5: 'B', 6: '选择', 7: 'X', 8: 'Y',
  9: '开始', 10: 'LB', 11: 'RB', 12: 'LT', 13: 'RT', 14: 'L3', 15: 'R3', 16: 'C', 17: 'Z',
  18: 'M1', 19: 'M2', 20: 'M3', 21: 'M4', 22: 'M5', 23: 'M6', 24: 'Fn', 25: '连发', 27: 'Home',
}
const TRIGGER_KEYS = [
  { id: 18, label: 'M1', bind: 'm1', pos: '背键右上' }, { id: 19, label: 'M2', bind: 'm2', pos: '背键左上' },
  { id: 20, label: 'M3', bind: 'm3', pos: '背键右下' }, { id: 21, label: 'M4', bind: 'm4', pos: '背键左下' },
  { id: 22, label: 'M5', bind: 'lm', pos: '头键左 (LM)' }, { id: 23, label: 'M6', bind: 'rm', pos: '头键右 (RM)' },
]
const TRIGGER_TYPES = [
  { id: 1, label: '单次', hint: '按一下触发一遍' },
  { id: 2, label: '按住循环', hint: '按住期间反复播放，松开即停' },
  { id: 3, label: '点击循环', hint: '按下开始循环，再按一下停止' },
]
const keyName = (k: number) => KEY_NAMES[k] ?? `键${k}`
const durOf = (m: Macro) => (m.actions.length ? m.actions[m.actions.length - 1].t : 0)
const MAX_MS = 655350                    // u16 tick × 10ms
const totalSteps = (list: Macro[]) => list.reduce((n, m) => n + m.actions.length, 0)

export default function Macros({ events, online }: { events: EngineEvent[]; online: boolean }) {
  const [macros, setMacros] = useState<Macro[]>([])
  const [version, setVersion] = useState(0)
  const [editIdx, setEditIdx] = useState<number | null>(null)   // null=新建
  const [edit, setEdit] = useState<Macro | null>(null)
  const [recording, setRecording] = useState(false)
  const [recStat, setRecStat] = useState({ steps: 0, seconds: 0 })
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const pollRef = useRef<number | undefined>(undefined)

  const refresh = () => api.macroConfig()
    .then(r => { setMacros(r.macros); setVersion(r.version); setMsg('') })
    .catch(e => setMsg(`✗ 读取失败：${(e as Error).message}`))
  useEffect(() => { refresh() }, [])
  // 设备从离线恢复时自动补一次读取（进页面时手柄还没插上的场景）
  const wasOnline = useRef(online)
  useEffect(() => {
    if (online && !wasOnline.current) refresh()
    wasOnline.current = online
  }, [online])

  // 录制中轮询后端步数（真实账本在固件侧采集器里，WS 事件只做实时反馈）
  useEffect(() => {
    if (!recording) return
    const tick = () => api.macroRecordStatus().then(setRecStat).catch(() => {})
    tick()
    pollRef.current = window.setInterval(tick, 300)
    const auto = window.setInterval(() => {   // 655s 自动封笔兜底
      api.macroRecordStatus().then(s => { if (!s.recording) stopRecord() }).catch(() => {})
    }, 2000)
    return () => { window.clearInterval(pollRef.current); window.clearInterval(auto) }
  }, [recording])

  const lastEvt = [...events].reverse().find(e => e.kind === 'extkey')
  const liveNames = recording && lastEvt ? (lastEvt.names as string[] | undefined) ?? [] : []

  const newMacro = () => {
    setEdit({ key_id: 18, type: 1, interval: 200, actions: [] })
    setEditIdx(null)
    setMsg('')
  }
  const openEdit = (i: number) => {
    setEdit({ ...macros[i], actions: macros[i].actions.map(a => ({ ...a })) })
    setEditIdx(i)
    setMsg('')
  }

  const startRecord = async () => {
    try {
      await api.macroRecordStart()
      setRecording(true); setMsg('')
    } catch (e) { setMsg(`✗ ${(e as Error).message}`) }
  }
  const stopRecord = async () => {
    try {
      const r = await api.macroRecordStop()
      setRecording(false)
      if (r.actions.length === 0) { setMsg('录制为空：没采到任何按键'); return }
      setEdit(ed => ed ? { ...ed, actions: r.actions } : ed)
      setMsg(`✓ 已录 ${r.actions.length} 步 / ${r.seconds}s`)
    } catch (e) { setRecording(false); setMsg(`✗ ${(e as Error).message}`) }
  }

  const validate = (m: Macro, list = macros): string | null => {
    if (!m.actions.length) return '没有动作：先录制，或从已有宏复制'
    if (m.actions.length > 64) return `动作数超上限（${m.actions.length}/64）`
    if (durOf(m) > MAX_MS) return '总时长超 655s'
    if (m.interval > 2540) return '循环间隔超 2540ms'
    if (list.some((x, i) => i !== editIdx && x.key_id === m.key_id))
      return `触发键 ${keyName(m.key_id)} 已被占用（一条触发键只能绑一个宏）`
    if (totalSteps(list) > 128)
      return `全部宏合计 ${totalSteps(list)} 步，超页容量 128 步`
    return null
  }

  const write = async (list = macros, unbind: string[] = []) => {
    setBusy(true); setMsg('写入中…（42 包读写校验 + 应用 + 保存，约 10s）')
    try {
      const r = await api.macroWrite(list, unbind)
      setMsg(`✓ 已写入 V${r.version}` +
        (r.warnings?.length ? ` ⚠ ${r.warnings.join('；')}` : ''))
      setEdit(null); setEditIdx(null)
      refresh()
    } catch (e) { setMsg(`✗ ${(e as Error).message}`) }
    setBusy(false)
  }

  const saveMacro = () => {
    if (!edit) return
    const list = [...macros]
    if (editIdx !== null) list[editIdx] = edit
    else list.push(edit)
    const problem = validate(edit, list)
    if (problem) { setMsg(`✗ ${problem}`); return }
    write(list)
  }
  const removeMacro = (i: number) => {
    const m = macros[i]
    if (!confirm(`删除 ${keyName(m.key_id)} 上的宏并写入设备？触发键将回到映射卡配置的状态（默认透传）。`)) return
    // ADR-032：键表由后端单一规则裁决，删除 = 列表少一条，触发键自动回落
    write(macros.filter((_, j) => j !== i))
  }
  const copyMacro = (i: number) => {
    const src = macros[i]
    const free = TRIGGER_KEYS.find(t => !macros.some(m => m.key_id === t.id))
    if (!free) { setMsg('✗ 没有空闲触发键：五颗键都被占用了，先删一条宏'); return }
    setEdit({ ...src, key_id: free.id, actions: src.actions.map(a => ({ ...a })) })
    setEditIdx(null)
    setMsg('')
  }
  const exportMacros = () => {
    const data = JSON.stringify({ kind: 'apex5-macros', version: 1, macros }, null, 1)
    const url = URL.createObjectURL(new Blob([data], { type: 'application/json' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `apex5-macros-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
  }
  const importMacros = (file: File) => {
    file.text().then(txt => {
      let list: Macro[]
      try {
        const data = JSON.parse(txt)
        list = Array.isArray(data) ? data : data.macros
      } catch { setMsg('✗ 导入失败：不是合法的 JSON'); return }
      if (!Array.isArray(list) || list.length > 5) { setMsg('✗ 导入失败：宏列表为空或超过 5 条'); return }
      const bad = list.find(m => !m.actions?.length || m.actions.length > 64
        || !TRIGGER_KEYS.some(t => t.id === m.key_id))
      if (bad) { setMsg('✗ 导入失败：存在缺动作/超 64 步/触发键不是拓展键的宏'); return }
      if (!confirm(`导入 ${list.length} 条宏并写入设备？当前设备上的宏将被替换。`)) return
      write(list)
    }).catch(() => setMsg('✗ 读文件失败'))
  }
  const backup = async () => {
    try { const r = await api.macroBackup(); setMsg(`✓ 已备份当前宏区（${r.macros} 条宏）`) }
    catch (e) { setMsg(`✗ ${(e as Error).message}`) }
  }
  const restore = async () => {
    if (!confirm('恢复备份的宏区并写入设备？只覆盖宏页、循环间隔和六颗拓展键的键表绑定，其余设置不动。')) return
    setBusy(true); setMsg('恢复中…')
    try { await api.macroRestore(); setMsg('✓ 已恢复备份宏区'); refresh() }
    catch (e) { setMsg(`✗ ${(e as Error).message}`) }
    setBusy(false)
  }

  const delAction = (i: number) => {
    // 成对删除：删「按下」连同它对应的「抬起」（反之亦然），保持配对合法
    setEdit(ed => {
      if (!ed) return ed
      const a = ed.actions[i]
      let j = -1
      if (a.ev === 1) {
        j = ed.actions.findIndex((x, k) => k > i && x.key === a.key && x.ev === 0)
      } else {
        for (let k = i - 1; k >= 0; k--) {
          if (ed.actions[k].key === a.key && ed.actions[k].ev === 1) { j = k; break }
        }
      }
      const drop = new Set(j >= 0 ? [i, j] : [i])
      return { ...ed, actions: ed.actions.filter((_, k) => !drop.has(k)) }
    })
  }

  // 设备离线：不出功能界面，直接给友好提示（插上手柄自动恢复，见 DeviceGate）
  if (!online) {
    return (
      <DeviceGate online={false} hint="板载宏存在手柄固件里，没连上手柄读不到也写不进。请检查 USB 线是否插好，或重新插拔一次手柄；连上后本页会自动读取配置。" />
    )
  }

  return (
    <div className="max-w-4xl space-y-4">
      {/* 标题行 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-[14px] font-medium">
          <Wand2 size={15} className="text-accent" /> 板载宏
          <span className="text-[11px] font-normal text-text-low">V{version} · 存在固件里，关掉本软件照样触发</span>
        </div>
        <div className="flex gap-2">
          <button className="btn !px-2.5 !py-1 text-[11px]" disabled={busy} onClick={refresh}>
            <RotateCcw size={12} /> 读取设备
          </button>
          <button className="btn !px-2.5 !py-1 text-[11px]" disabled={busy || !macros.length} onClick={exportMacros}>
            <Download size={12} /> 导出
          </button>
          <label className="btn !px-2.5 !py-1 text-[11px]" style={{ opacity: busy ? 0.5 : 1 }}>
            <Upload size={12} /> 导入
            <input type="file" accept=".json,application/json" className="hidden"
              onChange={e => { const f = e.target.files?.[0]; if (f) importMacros(f); e.target.value = '' }} />
          </label>
          <button className="btn !px-2.5 !py-1 text-[11px]" disabled={busy} onClick={backup}>备份</button>
          <button className="btn !px-2.5 !py-1 text-[11px]" disabled={busy} onClick={restore}>恢复备份</button>
        </div>
      </div>

      {/* 宏列表 */}
      <div className="card p-4">
        <div className="mb-3 flex items-center justify-between">
          <div className="text-[13px] font-medium">宏列表 <span className="text-text-low">({macros.length}/5 · 共 {totalSteps(macros)}/128 步)</span></div>
          <button className="btn btn-primary !px-3 !py-1.5 text-[12px]" disabled={busy || macros.length >= 5 || !!edit}
            onClick={newMacro}>
            + 新建宏
          </button>
        </div>
        {macros.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border-soft py-8 text-center text-[12px] text-text-low">
            设备里还没有宏。点「新建宏」→ 录一段按键 → 写入，第一个宏就住进手柄了。
          </div>
        ) : (
          <div className="space-y-1.5">
            {macros.map((m, i) => {
              const tk = TRIGGER_KEYS.find(t => t.id === m.key_id)
              return (
                <div key={i} className={`flex items-center gap-3 rounded-lg border px-3 py-2 text-[12px] ${
                  editIdx === i ? 'border-accent/50 bg-accent/8' : 'border-border-soft'}`}>
                  <span className="flex h-6 w-8 items-center justify-center rounded bg-accent/15 font-mono text-[11px] text-accent">
                    {tk?.label ?? keyName(m.key_id)}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-text-mid">{tk?.pos ?? ''}</span>
                  <span className="text-text-mid">{TRIGGER_TYPES.find(t => t.id === m.type)?.label ?? `类型${m.type}`}</span>
                  <span className="font-mono text-text-low">{m.actions.length} 步 · {(durOf(m) / 1000).toFixed(1)}s</span>
                  <button className="btn !px-2 !py-1 text-[11px]" disabled={!!edit || busy} onClick={() => openEdit(i)}>
                    <Pencil size={11} /> 编辑
                  </button>
                  <button className="btn !px-2 !py-1 text-[11px]" disabled={!!edit || busy} title="以这条宏的动作新建一条"
                    onClick={() => copyMacro(i)}>
                    <Copy size={11} />
                  </button>
                  <button className="btn !px-2 !py-1 text-[11px] text-err" disabled={busy} onClick={() => removeMacro(i)}>
                    <Trash2 size={11} />
                  </button>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* 编辑器 */}
      {edit && (
        <div className="card p-4">
          <div className="mb-3 text-[13px] font-medium">
            {editIdx !== null ? '编辑宏' : '新建宏'}
            <span className="ml-2 text-[11px] font-normal text-text-low">以触发键为名字：M1 的宏就是「M1 宏」</span>
          </div>

          {/* 基础属性 */}
          <div className="mb-4 flex flex-wrap items-end gap-4">
            <label className="text-[12px] text-text-mid">
              触发键
              <select value={edit.key_id} onChange={e => setEdit({ ...edit, key_id: +e.target.value })}
                className="mt-1 block rounded-lg border border-border-soft bg-[#0d0d14] px-2 py-1.5 text-[12px] text-text-hi outline-none focus:border-accent/60">
                {TRIGGER_KEYS.map(t => (
                  <option key={t.id} value={t.id}>{t.label}（{t.pos}）</option>
                ))}
              </select>
            </label>
            <div className="text-[12px] text-text-mid">
              触发方式
              <div className="mt-1 flex gap-1">
                {TRIGGER_TYPES.map(t => (
                  <button key={t.id} title={t.hint} onClick={() => setEdit({ ...edit, type: t.id })}
                    className={`rounded-lg px-2.5 py-1.5 text-[12px] transition-colors ${
                      edit.type === t.id ? 'bg-accent/15 text-accent' : 'text-text-mid hover:bg-white/4'}`}>
                    {t.label}
                  </button>
                ))}
              </div>
            </div>
            {edit.type !== 1 && (
              <label className="text-[12px] text-text-mid">
                循环间隔 <span className="font-mono text-accent">{edit.interval}ms</span>
                <input type="range" min={30} max={2540} step={10} value={edit.interval}
                  onChange={e => setEdit({ ...edit, interval: +e.target.value })} className="mt-1 block w-32 accent-[#22d3ee]" />
              </label>
            )}
          </div>

          {/* 录制区 */}
          <div className="mb-4 rounded-lg border border-border-soft p-3">
            <div className="flex items-center gap-3">
              {recording ? (
                <>
                  <button className="btn btn-danger !px-3 !py-1.5 text-[12px]" onClick={stopRecord}>
                    <CircleStop size={13} /> 停止录制
                  </button>
                  <span className="flex items-center gap-1.5 text-[12px] text-err">
                    <Circle size={9} className="animate-pulse fill-err" />
                    录制中 {recStat.steps} 步 / {recStat.seconds}s
                  </span>
                  <span className="text-[11px] text-text-low">
                    {liveNames.length ? `正在按：${liveNames.join(' + ')}` : '按下手柄上的按键…（拓展键是触发键，不录进动作）'}
                  </span>
                </>
              ) : (
                <>
                  <button className="btn btn-primary !px-3 !py-1.5 text-[12px]" onClick={startRecord} disabled={busy}>
                    <Play size={13} /> {edit.actions.length ? '重新录制' : '开始录制'}
                  </button>
                  <span className="text-[11px] text-text-low">
                    像玩游戏一样按一遍，按下与抬起都会被记下来（单条上限 64 步 / 655s，10ms 精度）
                  </span>
                </>
              )}
            </div>
          </div>

          {/* 时间轴 */}
          {edit.actions.length > 0 && (
            <div className="mb-4">
              <div className="mb-1.5 flex items-center justify-between text-[12px] text-text-mid">
                <span>时间轴 <span className="text-text-low">({edit.actions.length} 步 · {(durOf(edit) / 1000).toFixed(2)}s)</span></span>
                <button className="btn !px-2 !py-0.5 text-[11px]" onClick={() => setEdit({ ...edit, actions: [] })}>清空</button>
              </div>
              {/* 时间轴条：按下=亮块 抬起=暗块 */}
              <div className="relative mb-2 h-6 overflow-hidden rounded bg-[#0d0d14]">
                {edit.actions.map((a, i) => {
                  const dur = Math.max(durOf(edit), 1)
                  const w = Math.max(0.8, (i < edit.actions.length - 1 ? edit.actions[i + 1].t - a.t : 50) / dur * 100)
                  return (
                    <div key={i}
                      title={`${a.t}ms ${keyName(a.key)} ${a.ev === 1 ? '按下' : '抬起'}`}
                      className={`absolute top-0 h-full ${a.ev === 1 ? 'bg-accent/60' : 'bg-white/10'}`}
                      style={{ left: `${a.t / dur * 100}%`, width: `${w}%` }} />
                  )
                })}
              </div>
              <div className="max-h-44 space-y-0.5 overflow-y-auto">
                {edit.actions.map((a, i) => (
                  <div key={i} className="group flex items-center gap-2 rounded px-2 py-0.5 text-[11px] hover:bg-white/4">
                    <span className="w-14 text-right font-mono text-text-low">{a.t}ms</span>
                    <span className={`w-10 font-mono ${a.ev === 1 ? 'text-ok' : 'text-text-mid'}`}>{keyName(a.key)}</span>
                    <span className={a.ev === 1 ? 'text-accent' : 'text-text-low'}>{a.ev === 1 ? '按下' : '抬起'}</span>
                    <button className="ml-auto hidden text-err group-hover:block" title="删除此步"
                      onClick={() => delAction(i)}><Trash2 size={11} /></button>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="flex items-center gap-2">
            <button className="btn btn-primary" disabled={busy || recording} onClick={saveMacro}>
              <Save size={13} /> 写入设备
            </button>
            <button className="btn" disabled={busy} onClick={() => { setEdit(null); setEditIdx(null) }}>取消</button>
            {msg && <span className="text-[12px] text-text-mid">{msg}</span>}
          </div>
        </div>
      )}
      {!edit && msg && <div className="text-[12px] text-text-mid">{msg}</div>}

      {/* 说明 */}
      <div className="card p-4 text-[11px] leading-relaxed text-text-low">
        写入即存进手柄当前配置槽并自动把触发键切到宏模式（键表 target=32）：游戏里按对应拓展键就播放宏，
        关掉本软件照样触发，与扳机/震动联动互不干扰。删除宏会把它的触发键还原成透传。
        限制：≤5 条宏、单条 ≤64 步 / 655s、全部宏合计 ≤128 步、时间精度 10ms。
        宏与键位映射存在同一份配置里，「备份」会连同当时整个配置槽一起存下。首次使用建议先点一次。
      </div>
    </div>
  )
}
