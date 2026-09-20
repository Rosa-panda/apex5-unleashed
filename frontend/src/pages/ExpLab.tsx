// 体验区（ADR-026）：隐藏功能孵化区。功能清单由后端注册表下发（/api/exp），
// 前端只渲染——上架/转正/淘汰都不用改这里。真机测过判「好用」的功能才迁出体验区。
import { useCallback, useEffect, useState } from 'react'
import { FlaskConical, ThumbsDown, ThumbsUp, PauseCircle, ChevronDown, ChevronUp } from 'lucide-react'
import { api, type ExpFeature, type ExpList } from '../api'
import { PANELS } from './exp/panels'

const VERDICT_STYLE: Record<string, string> = {
  good: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300',
  bad: 'border-red-500/40 bg-red-500/10 text-red-300',
  pending: 'border-border-soft bg-white/5 text-text-mid',
}
const VERDICT_TEXT: Record<string, string> = {
  good: '好用', bad: '不好用', pending: '待测',
}
const TIER_STYLE: Record<number, string> = {
  1: 'border-accent/40 bg-accent/10 text-accent',
  2: 'border-violet-500/40 bg-violet-500/10 text-violet-300',
  3: 'border-border-soft bg-white/5 text-text-low',
}

function FeatureCard({ f, open, onToggle, onVerdict }: {
  f: ExpFeature
  open: boolean
  onToggle: (id: string) => void
  onVerdict: (id: string, v: 'good' | 'bad' | 'pending') => void
}) {
  const Panel = PANELS[f.id]
  return (
    <div className={`card flex flex-col gap-2 p-4 ${f.verdict === 'bad' ? 'opacity-60' : ''}`}>
      <div className="flex items-center gap-2">
        <span className="text-[13px] font-semibold text-text-hi">{f.title}</span>
        <span className={`rounded border px-1.5 py-0.5 text-[10px] ${TIER_STYLE[f.tier]}`}>
          {f.tierLabel}
        </span>
        {f.enabled
          ? <span className="rounded border border-accent/40 bg-accent/10 px-1.5 py-0.5 text-[10px] text-accent">可测试</span>
          : <span className="rounded border border-border-soft bg-white/5 px-1.5 py-0.5 text-[10px] text-text-low">规划中</span>}
        <span className="ml-auto text-[10px] text-text-low">{f.plan}</span>
      </div>
      <p className="text-[11px] leading-relaxed text-text-mid">{f.desc}</p>
      {f.id in PANELS && (
        <button
          className="flex items-center gap-1 self-start text-[11px] text-accent hover:underline"
          onClick={() => onToggle(f.id)}>
          {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          {open ? '收起面板' : '展开功能面板'}
        </button>
      )}
      {open && (
        <div className="rounded-md border border-border-soft bg-black/20 p-3">
          <Panel />
        </div>
      )}
      <div className="mt-auto flex items-center gap-1.5 pt-1">
        <button
          className={`flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] transition-colors ${
            f.verdict === 'good' ? VERDICT_STYLE.good : 'border-border-soft text-text-low hover:border-emerald-500/40 hover:text-emerald-300'}`}
          onClick={() => onVerdict(f.id, 'good')}
          title="真机测试通过：转正候选">
          <ThumbsUp size={12} /> 好用
        </button>
        <button
          className={`flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] transition-colors ${
            f.verdict === 'pending' ? VERDICT_STYLE.pending : 'border-border-soft text-text-low hover:border-border-soft hover:text-text-mid'}`}
          onClick={() => onVerdict(f.id, 'pending')}
          title="还没测或测到一半">
          <PauseCircle size={12} /> 待测
        </button>
        <button
          className={`flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] transition-colors ${
            f.verdict === 'bad' ? VERDICT_STYLE.bad : 'border-border-soft text-text-low hover:border-red-500/40 hover:text-red-300'}`}
          onClick={() => onVerdict(f.id, 'bad')}
          title="真机测试不理想：标记淘汰或回炉">
          <ThumbsDown size={12} /> 不好用
        </button>
        <span className="ml-auto text-[10px] text-text-low">
          当前：{VERDICT_TEXT[f.verdict] ?? f.verdict}
        </span>
      </div>
    </div>
  )
}

export default function ExpLab() {
  const [data, setData] = useState<ExpList | null>(null)
  const [msg, setMsg] = useState('')
  const [openId, setOpenId] = useState<string | null>(null)

  const load = useCallback(() => {
    api.expList().then(setData).catch(() => setMsg('✗ 加载失败'))
  }, [])
  useEffect(() => { load() }, [load])

  const flash = (t: string) => { setMsg(t); setTimeout(() => setMsg(''), 3000) }
  const onVerdict = (id: string, v: 'good' | 'bad' | 'pending') => {
    api.expVerdict(id, v)
      .then(() => { flash(v === 'good' ? '✓ 已记「好用」——转正候选' : v === 'bad' ? '✓ 已记「不好用」——回炉/淘汰' : '✓ 已记「待测」'); load() })
      .catch(() => flash('✗ 判定保存失败'))
  }

  const feats = data?.features ?? []
  const grouped: Array<[number, ExpFeature[]]> = [1, 2, 3].map(t => [t, feats.filter(f => f.tier === t)])
  const s = data?.summary

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div className="card p-5">
        <div className="mb-2 flex items-center gap-2 text-[12px] text-text-mid">
          <FlaskConical size={14} className="text-accent" /> 体验区 · 隐藏功能孵化区
          {s && (
            <span className="ml-auto flex items-center gap-2 text-[11px]">
              <span className="text-emerald-300">好用 {s.good}</span>
              <span className="text-red-300">不好用 {s.bad}</span>
              <span className="text-text-low">待测 {s.pending}</span>
            </span>
          )}
        </div>
        <p className="text-[12px] leading-relaxed text-text-mid">
          这里收容逆向挖出来的全部隐藏功能（16 项）。每项做出来先放在这，<b className="text-text-hi">真机试过、判「好用」才转正进正式页面</b>；
          不好用的标记淘汰。功能逐项上架，上架后卡片出现「可测试」徽标。
          判定记录存在数据文件夹（exp_verdicts.json），重启不丢。
        </p>
        {msg && <div className="mt-2 text-[12px] text-accent">{msg}</div>}
      </div>

      {grouped.map(([tier, list]) => list.length > 0 && (
        <div key={tier} className="space-y-2">
          <div className="px-1 text-[11px] text-text-low">
            {tier === 1 ? '第一梯队 · 核心玩法' : tier === 2 ? '第二梯队 · 生态与管理' : '第三梯队 · 补全与实验'}
          </div>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {list.map(f => (
              <FeatureCard key={f.id} f={f} open={openId === f.id}
                onToggle={id => setOpenId(cur => (cur === id ? null : id))}
                onVerdict={onVerdict} />
            ))}
          </div>
        </div>
      ))}

      {!data && <div className="text-[12px] text-text-low">加载中…</div>}
    </div>
  )
}
