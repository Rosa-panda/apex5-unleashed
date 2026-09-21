# ADR-028 体感中心：独立栏目 + 总闸 + 丝滑试玩场

日期：2026-09-21 ｜ 状态：已实施 ｜ 上游：ADR-026/027（体验区）、ADR-027 v-sleep（运动流省电开关）

## 背景

用户驱动：①体感功能埋在体验区不合理——「大部分游戏不需要体感，开了体感才用得上」，
应有独立栏目 + 总开关，用时开、用完关（顺手解决耗电）；②迷宫弹珠质感要向手机
弹珠游戏看齐（丝滑滚动），作为体感手感的试金石；③体验区里被转移的旧功能摘除。

调研（联网）：丝滑滚动的公认做法 = 固定步长物理 + 高子步数（防穿墙，matter-js
0.20 substepping / issue #619 的结论）、输入低通、球体自转视觉与碰撞音效反馈
（手机 labyrinth 类游戏的质感来源）。参考项目：Neverball（tilt-floor 开山）、
Super Monkey Ball（WebMonkeyBall 重制）、A-maze Ball（matter.js 木盒迷宫）。
**依赖决策（用户拍板，2026-09-21 反转）**：曾先做零依赖自研物理，用户纠正——
「不能重复造轮子，别人调了一年多的轮子凭什么自己弄」，但要求「依赖无感」：GitHub
拿到项目的人开箱即用、不需要再装依赖。结论：matter.js 是**构建时打包**进前端
产物（~80KB 进 bundle），终端用户拿到的后台+前端零 npm 感知——成熟轮子与
开箱即用不冲突，换 matter.js。自研版作废。

## 决策

### D1 信息架构
- 新顶级导航「体感」（frontend/src/pages/Motion.tsx），四模块：
  - 总闸（本 ADR D2）
  - 软件层陀螺→鼠标（原体验区 #1，组件 GyroPanel 复用）
  - 固件层陀螺→摇杆（原 #6，GyroFwPanel）
  - 模拟器桥 DSU（原 #18，DsuPanel）
  - 试玩场（原 #17 迷宫的完全升级版，见 D3）
- explab.py FEATURES 摘除 gyro/gyrofw/maze/dsu 四项（体验区列表不再显示）；
  判定账本（exp_verdicts.json）保留不迁——历史证据仍在。端点 /api/exp/* 全部
  原样保留（新栏目复用同一批端点，不另起炉灶）。

### D2 总闸语义（联动，不是第四个开关）
- POST /api/motion/master {enabled}：
  - 关闸 = 运动流 cmd17 raw=0 + DSU 桥 stop + 陀螺瞄准 enabled=false
    （一关全关，固件恢复自动休眠——省电是默认态）
  - 开闸 = 运动流 raw=1 + DSU 桥 start（桥常备无成本）；陀螺瞄准不自动开
    （尊重用户上次的选择，开闸后自己在模块里开）
- GET 返回聚合状态（raw 流/DSU/陀螺瞄准 各自 enabled），总闸 UI 一眼看清
- 既有 GyroPanel「运动流」单开关保留为裸开关（总闸的底层执行器）
- ~~RAM 态不持久化~~ → 已反转，见下方 D2 补充：状态持久化，attach 服从持久态

### D3 试玩场：丝滑物理（matter.js）
旧 MazeBoard（单步欧拉、碰撞浅轴弹出）升级为「木盒弹珠」质感：
- **物理引擎 matter.js**（D2 依赖决策）：`Engine.create` + 静态墙矩形 + 球体
  （restitution 0.42 / frictionAir 0.008）；tilt 直灌 `engine.gravity` 向量——
  引擎自己处理碰撞与积分
- **固定步长 + 子步**：`Engine.update(engine, 1000/240)` 每帧 4 子步 + 速度钳制
  （MAXV≈745 px/s）——matter 0.20 官方防穿墙姿势，帧率无关
- **输入低通**：后端 tilt 40ms 轮询本身有阶梯感，前端再加一阶低通（α≈dt*14），
  手柄抖动不直接进重力向量
- **滚动质感**：球自转纹理（spin += v·dt/r，三条纬线沿速度轴转动）；洞口低速
  吸入（速度阈值 340 px/s + 朝洞心 pull）——快速掠过不陷，引力感
- **反馈**：collisionStart 相对法向速度 → WebAudio 合成音（WebAudio 现场合成，
  零素材）+ 手柄震动（engine.set_rumble，强度∝撞击速度，130ms 节流）；
  视觉：板子随 tilt 微倾微缩（Neverball 式「板是活的」）、球渐变+阴影随倾斜偏移、
  洞径向渐变、木盒配色
- 计时/最佳/落洞计数/重开一局保留
- 仍用后端 /api/exp/maze tilt（解算不重复造）；面板保留原始遥测自检区

### D2 补充（用户追加）：总闸状态持久化
- 「默认关，但不想每次开软件都手动关」→ 状态存
  %APPDATA%\Apex5Unleashed\motion_hub.json（{"master": bool}）
- 首次运行默认关；上次开 → 本次启动自动恢复（raw 流 + DSU 桥）
- attach 不再无条件 raw=1：服从持久态——关闸用户重连手柄不被悄悄重开流
- engine.raw_motion 初值改 False（总闸真相源），由启动恢复/总闸端点写回

### D4 不做的事
- 不做关卡系统/排行榜（试玩场是手感调校工具，不是游戏产品）
- 不动 gamesim 靶场/键盘场（那些测的是摇杆映射/连发/宏，留在体验区合理）
- DSU 轴向符号钩子不变（等 Yuzu 真机验收）

## 实现记录

- backend：service.py /api/motion/master GET/POST（编排 raw+dsu+gyro 三开关）；
  explab.py 摘除四项；端点全保留
- frontend：pages/Motion.tsx（总闸卡 + 四模块布局）；App.tsx 导航加「体感」
  （Orbit 图标）；panels.tsx PANELS 注册表移除四项（组件保留导出）；
  MazeBoard 物理核心换 matter.js（240Hz 子步 + collisionStart 反馈）
- npm 依赖：matter-js + @types/matter-js（构建时打包进 bundle，终端用户零感知）
