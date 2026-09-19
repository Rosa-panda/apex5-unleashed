// 全局错误边界：页面渲染崩溃不再黑屏，错误文本直接上屏 + 上报后端日志（apex5.log）。
import { Component, type ErrorInfo, type ReactNode } from 'react'
import { api } from './api'

interface Props { children: ReactNode; page: string }
interface State { error: Error | null }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    const stack = `${error.stack ?? ''}\n--- 组件栈 ---\n${info.componentStack ?? ''}`
    api.uiError(error.message, stack, `page=${this.props.page}`)
  }

  componentDidUpdate(prev: Props) {
    // 切页时清掉旧错误，给新页面机会正常挂载
    if (prev.page !== this.props.page && this.state.error) this.setState({ error: null })
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="card p-4 text-[12px] leading-relaxed">
        <div className="mb-2 font-medium text-err">页面渲染出错（{this.props.page}）</div>
        <div className="mb-2 text-text-mid">{this.state.error.message}</div>
        <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded bg-[#0d0d14] p-2 font-mono text-[10px] text-text-low">
          {this.state.error.stack ?? ''}
        </pre>
        <button className="btn mt-3 !px-3 !py-1.5 text-[12px]"
          onClick={() => this.setState({ error: null })}>
          重试
        </button>
      </div>
    )
  }
}
