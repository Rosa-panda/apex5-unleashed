# ADR-029 全项目结构解耦（行为零变化）

日期：2026-09-22 ｜ 状态：已批准实施 ｜ 诱因：ADR-028 修订 2 的 0xEF 需求登记表散在 service.py 闭包里，靠「定义先于使用」的书写顺序维系，一次 import 顺序疏漏炸掉启动（NameError: threading）。用户拍板：「全项目不动逻辑，但是整体架构感觉需要一个优化」「这个问题我怕下次修改还会这样」。

## 原则

**只动「代码住在哪」，不动「代码做什么」。** 端点路径/语义、协议字节、时序常量（心跳 15s/看门狗 30s/WS 推送 30Hz/各页轮询间隔）、UI 渲染结果、main.py 启动时序全部原样。每批独立 commit + 独立验收，可单独回退。

## 现状

- backend/app/service.py 1490 行 = create_app 单函数：110 路由 + ~15 闭包辅助 + ~50 处函数内延迟 import，全部内联。
- 组装点分裂：main.py 构造 engine/store/games/ingress/mods 传入；RgbBridge/Diagnostics/maze.SERVICE/DsuServer/RawStreamHub 却在 create_app 内联实例化。
- engine.py 780 行单类（事件总线/0xEF 解码/代理仲裁/HID 生命周期/LED/屏幕/扳机业务）。
- 前端 exp/panels.tsx 1381 行 18 面板单文件；api.ts 240 行 90+ 函数扁平；无 components\ 无共享 hook；App.css 死文件。
- 已有的好模式（本次遵循）：rawstream.RawStreamHub（独立模块+登记表+FakeEngine 单测）、games.subscribers、transport HidPad/MockPad。

## 决策

### D1 router 依赖注入：工厂闭包，不用 Depends
`build_xxx_router(ctx) -> APIRouter`，闭包捕获 ctx 属性——与现状闭包语义逐字等价，零行为风险。Depends 会改请求期解析路径，属行为面变更，不用。

### D2 Pydantic Req 模型随 router 走
每个 Req 只被一个域使用；跨域共享的极少数放 routers/schemas.py。集中式 schemas.py 会造出第二个 1490 行式堆积点。

### D3 组装收进 appctx.py 的 AppContext.build()（create_app 内构造），main.py 一字不动
main.py 启动时序敏感（单实例探测/端口重试/uvicorn/webview/托盘）是明令红线。组装分裂的本质问题在 create_app 内联那段（exp 服务群+五处 subscribe 接线），收进 ctx.build() 后 create_app 只剩一个显式组装点。**搬迁时按现行行序逐行搬**（订阅顺序敏感：bus.publish 必须先于 RECORDER.on_event；总闸恢复序列 _hub→DSU start→_raw.eval 不可换）。

### D4 on_event→lifespan 本轮不动
WS 事件循环捕获（loop_ref 赋值时序）挂在 startup 事件上，改 lifespan 是行为面赌博。技术债注记保留。

### D5 engine.py 本轮不拆
1. 它是「运行时单核」而非上帝类堆积：HID 读线程/事件总线/代理仲裁/看门狗共享 _stop 与线程句柄，拆开引入跨对象锁序问题——行为面风险，非结构面收益。
2. 消费面太宽：main.py 直捅 eng._stop/_emit，tray/games/mods/13 个测试直接属性访问；拆=全项目一次性大改，违背分批可回退。
3. rawstream/games.subscribers 证明新能力可增量长在外部，存量不拆无维护灾难。
4. 未来若拆：第一步只抽 EventBus（subscribe/subscribe_motion/_emit）为独立模块、Engine 组合它、API 面不变——届时另立 ADR。

## 目标目录形态

```
backend/app/
  service.py        # 终态 <80 行：ctx → include_router ×13 → 中间件 → return
  appctx.py         # AppContext（参数 + exp 服务群，build() 按现行行序构造）
  wsbus.py          # WsBus（clients/loop_ref/publish/grab_loop/attach）
  motionmaster.py   # MotionMaster（总闸持久化/探针日志/30Hz to_ws）
  routers/          # common(err) system ws control led screen extkeys macro
                    # presets games settings explab motion
frontend/src/
  api/              # http types system control presets games macros screen
                    # lights motion exp settings index（api/index.ts 合并导出，
                    # 调用点 import 不变）
  pages/exp/ui.tsx + pages/exp/panels/*.tsx   # panels.tsx 改 barrel（PANELS 键序不变）
  components/ hooks/                          # Row/Toggle/Section/Chip + usePolling
```

## 实施批次

B0 本 ADR → B1 wsbus/motionmaster/appctx 骨架 → B2 routers 骨架+system+ws → B3 control+led → B4 screen+extkeys+macro → B5 presets+games → B6 settings → B7 AppContext.build+explab → B8 motion+收口 → F1 api 拆域 → F2 panels 拆分 → F3 components+usePolling → F4 App.css 删除+App.tsx 整理。每批验收：后端 12 个离线测试 + mock 启动 health + 基线响应 diff（拆前先存）+ 前端 npm run build + 页面点验。

## 非目标（防爆仓）

1. protocol/transport/0xEF 解码一切 HID 字节不动。
2. main.py 不动（create_app 签名不变）。
3. index.css Tailwind 令牌不动；BTN 常量与全局 .btn 并行现状保留（只在 exp/ui.tsx 内收敛）。
4. on_event→lifespan 不改；engine.py 不拆；前端 any 不补；React Context 不引入、props 下钻保持（重渲染边界是行为面）。
5. 不做 Depends 改造、不合并重复端点、不顺手改任何返回结构。
6. 所有时序常量、WS 队列 maxsize、30Hz 节流、favicon 全内存生成等逐字保留（含注释——py-spy 实锤警告是行为约束的一部分）。
7. 函数内延迟 import 搬迁时保持函数级原位（防循环导入与模块加载时序变化）。

## 风险与对策

- 订阅顺序/总闸恢复序列错位 → 搬前抄 checklist 逐项对勾；验收含总闸开着重启 DSU 自回。
- 闭包变量提升漏改、局部 import 新作用域 NameError（py_compile 查不出）→ 每批必须实际启动后端 + health。
- PANELS 键序/漏注册 → barrel 导出面 grep 对照；tsc 兜底 Motion.tsx 具名导入。
- 轮询间隔误统一 → usePolling 间隔以调用点字面量为准，逐页小 commit 便于 bisect。

## 修订 1（2026-09-22，F2 实施中勘察后的 F3 收缩）

F3 勘察实锤：Row/Toggle/Section/Chip **各自只有一个实现**，且形态互异——Settings 的 Row 是 `{k,v}` 键值文本、exp/ui.tsx 的 Row 是 `{label,children}` 容器；PresetLibrary 的 Section 是组件内局部闭包；Chip 仅 Motion.tsx 一处；Toggle 仅 Settings.tsx 一处。**没有第二个使用者，抽进 components/ 是搬家不是去重**，反而在 Barrel 之外多一层间接。据此收缩：

- **F3 只抽 `hooks/usePolling.ts(fn, intervalMs, deps)`**，替换 8 处标准形态轮询（GameLibrary 3s / Motion 2s / gyro 1s / rgbbridge 2s / gamesim 1.5s / dsu 600ms / maze 遥测 300ms / maze HUD 强刷 200ms）。
- **不建 components/ 目录**，Row/Toggle/Section/Chip 维持原位原样。
- 不动 diagnostics（条件轮询：running 时 400ms、空闲 700ms setTimeout——非标准形态，强套改行为结构）、Macros（录制 tick）/Lights（动画帧）/PadTest（15s 原始流心跳，语义非轮询）。
- usePolling 签名允许传 deps（GameLibrary/gamesim/Motion 的 effect 依赖 `[load]` 须保留）；各调用点 catch 行为随 fn 原样带走。
