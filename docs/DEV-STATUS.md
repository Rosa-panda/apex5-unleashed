# DEV-STATUS · 当前开发状态锚点

> **文档性质**：活文档（RISK-REGISTER **R8 · 巴士因子 = 1** 的应对锚点）。
> 本文回答「**我现在该怎么办**」——指向权威文档而**不是复制**其内容；每条都能落到可执行动作。
>
> - 版本基线：**v0.3.2**（仓库根 `VERSION` 为唯一真相源）
> - 权威分工：`docs/PRD.md`（做什么/为什么） · `docs/ARCHITECTURE.md`（代码怎么组织） ·
>   `docs/PROTOCOL.md`（字节怎么排） · `docs/TECH-SPEC.md`（技术参数与线程约定） ·
>   `docs/adr/`（逐个决策的来龙去脉） · `docs/TASK-BREAKDOWN.md`（任务分解）
> - **本文只做索引与状态记录**，结论一律引用上述文档；发现本文与代码不符时改文档，不改代码。
> - 状态锚点时间戳：**2026-10-06 15:20 (+08:00)**，基线提交见 §2 安全点。

### 状态标注纪律（2026-10-06 立，TASK-BREAKDOWN 全局纪律第 6 条）

每个状态标记必须是下列三种判定之一，**禁止预写 ✅**（文档先于代码落地是本项目的反面教材）：

| 标记 | 含义 | 要求 |
|---|---|---|
| ✅ | 命令可验证且**已复跑通过** | 必须附一条可当场复跑的命令 |
| ❌ | 命令可验证但未通过 | 必须附失败命令与输出 |
| ⚠ | **不可命令行验证**（需真机 / 需人工） | 既不默认放行也不默认挂掉，交人工判定 |
| ⬜ | 计划 / 本次不做 | —— |

> 引用者一律**以自己重跑的结果为准**，不要采信本文快照——同日早前曾出现「文档标 ✅ 但文件尚未创建」的事故。

---

## 1. 当前版本与来源

| 项 | 值 | 来源 / 校验方式 |
|---|---|---|
| 当前版本 | `0.3.2` | 仓库根 `VERSION`（唯一真相源，禁止在界面硬编码，PRD §4.2） |
| 运行期查询 | `GET /api/version` | `backend/app/routers/system.py`；frozen 态 `VERSION` 由 `apex5.spec` 打进 `_MEIPASS` |
| 构建元数据 | `GIT_SHA`（仓库根，CI 落盘） | `.github/workflows/release.yml`「落盘构建元数据」步骤；存在时 `/api/version` 一并返回短哈希，用于区分 nightly 来源 |
| 版本一致性校验 | `python tools/check_version.py` | CI 发版第一步；失败即中断打包 |
| 发布方式 | push main / push tag 自动打包发版 | 见 `docs/RELEASE.md`（发版 SOP） |

---

## 2. 安全点与回退方式

| 安全点 | 标识 | 用途 |
|---|---|---|
| 提交 | `c94f092` | 规范化改造前的最后一致状态 |
| 标签 | `safe-20261006-pre-standardization` | **推荐回退锚点** |
| 分支 | `backup/pre-standardization-20261006` | 备份分支，兜底用 |

**回退**：任何改动出问题立刻执行——

```powershell
git reset --hard safe-20261006-pre-standardization
```

> ⚠ **真机上不要「边调边试」**（全球只有一个手柄，RISK R4）。行为与改造前不一致时先回退、再记录现象、
> 最后才改代码（流程见 `docs/TASK-BREAKDOWN.md` T05）。

---

## 3. 已实现能力清单

> 完整的逐条需求、优先级与状态见 **`docs/PRD.md` §3 需求池**（P0 ×14 / P1 ×14 / P2 ×8）；
> 能力域到模块的映射见 **`docs/PRD.md` 附录 A**。本节只给状态快照，不复制正文。

| 能力域 | 状态 | 详情指向 |
|---|---|---|
| 协议引擎 / 设备生命周期 | ✅ | PRD P0-1；ADR-010/011/012 |
| 扳机实验室 / 预设库 | ✅ | PRD P0-2/P0-3；ADR-003 |
| 游戏库 / 五档适配 | ✅ | PRD P0-4/P0-5；ADR-008/014/017/022/024 |
| Mod 管家 / DSX ingress | ⚠ 端到端收包待真机 | PRD P0-6/P0-7；ADR-025（F1 23 收包待真机实测，**命令行无法验证**） |
| 板载宏 | ✅ | PRD P0-8；ADR-021/032 |
| 拓展键（一等键语义） | ✅ | PRD P0-9；ADR-016/019/030/031 |
| 灯光工坊 / 屏幕 | ✅ | PRD P0-10/P0-11；ADR-018/033/034 |
| 体感中心（总闸 + 四件套） | ✅ | PRD P0-12；ADR-027/028 |
| 状态与可观测性 / 写安全网 | ✅ | PRD P0-13/P0-14；ADR-006/013 |
| 测试区（体验区孵化） | ✅ | PRD P1-11；ADR-026/027 |

**明确非目标（改需求前必读）**：`docs/PRD.md` §5 边界条款 N1–N13。

---

## 4. 当前进行中 / 下一步

### 4.1 进行中（规范化改造，本次）

| 任务 | 优先级 | 状态 | 验证方式（可复跑） | 指向 |
|---|---|---|---|---|
| T01 文档收口（DEV-STATUS / ADR-INDEX / TEST-PLAN / RISK-REGISTER / README 索引 / PROTOCOL 死链） | P0 | ✅ 已完成 | `git ls-files docs/PRD.md docs/ARCHITECTURE.md docs/TASK-BREAKDOWN.md docs/DEV-STATUS.md`（4 行均有输出） | TASK-BREAKDOWN T01 |
| T02 工程卫生（临时脚本归位、`.design-refs/` 出仓库、`.gitignore` 补齐、前端 chunk 拆分） | P1 | ✅ 已完成 | `git ls-files tools/` 有 7 行；`git ls-files backend/app/_maze_check.py` **应为空**（已移出） | TASK-BREAKDOWN T02 |
| T03 CI 与发布闭环（测试门禁 workflow、smoke 脚本化、脚本式单测纳门禁、发版 SOP） | P2 | ✅ 已完成 | `python -m pytest backend -q` → `35 passed`；`python tools/run_smoke.py` → `ALL SMOKE OK` + exit 0 | TASK-BREAKDOWN T03 |
| T04.1 `protocol.py` 纯函数用例 | P3 | ✅ 已完成 | `python -m pytest backend/test_protocol_units.py -q` → `20 passed` | TASK-BREAKDOWN T04.1 |
| T04.2 – T04.5 测试补强（gameprofiles / payload / engine 账本 / trace 回放） | P3 | ⬜ 本次不做，留给后续迭代 | —— | TASK-BREAKDOWN T04 |
| T05 真机人工验收 | P1 | ⚠ **待人工**（需手柄，命令行无法验证，见 §7） | —— | TASK-BREAKDOWN T05 |

### 4.2 下一步候选（README「下一步」四项，尚未开工）

| # | 候选 | PRD 编号 | 当前决定 |
|---|---|---|---|
| 1 | 屏幕动画打磨（GIF 帧范围裁剪、状态栏常亮开关、恢复出厂入口） | P2-1 | 待办 |
| 2 | XGameMonitor 型 Mod 真机抽测 | P2-2 | 待办（**需真机**） |
| 3 | 统一游戏配置格式 `apex5-game-config/1` | P2-3 | **PRD §6 Q1 的建议答案**：优先做它（分享码生态与社区贡献路径的地基） |
| 4 | 分享码社区生态（社区配置仓库 + 应用内更新） | P2-4 | 待办（依赖第 3 项） |

> **拍板入口**：`docs/PRD.md` §6 待确认问题 Q1–Q6（Q1「v0.4 先做哪项」建议先做 ADR-015；
> Q2 灯表 10 帧容量怎么产品化；Q3 ADR-015 实现范围；Q4 临时/敏感素材归属；Q5 ExpLab 转正机制；Q6 硬件支持范围）。

---

## 5. 已知问题与坑位

### 5.1 协议层（PROTOCOL.md「已知坑」，勿重踩）

| 坑 | 说明 |
|---|---|
| 效果锁存 | `docs/PROTOCOL.md` §传输：所有效果锁存固件，**不发清除不会消失** → 实验前先 panic 基线 |
| ACK 成功位偏移 | 非 K6 命令看 `body[3]`，K6 家族看 `body[5]` |
| `side=3`（Both） | 会被 ACK 但不执行——双侧必须分别发 L 和 R |
| 官方软件抢灯（PROTOCOL 之外，ADR-033 修订 4） | 飞智空间站后台服务会把设备改回官方灯模式；用工具箱前请退出官方驱动 |

### 5.2 未消除风险（RISK-REGISTER，最后评审 v0.3.2）

| # | 风险 | 等级 | 状态 |
|---|---|---|---|
| R3 | 官方固件更新改协议 | 中 | 启动自检（cmd1 + 81 回显）；README 记录验证固件版本 |
| R4 | 硬件在环单点（全球 1 个手柄） | 高 | Mock 已入 v0.1；**trace 回放待办（PRD P2-6）** |
| R6 | HID 总线满负荷上限未探明 | 中 | 待做，**需真机探针压测（需人工，不进 CI）** |
| R8 | 巴士因子 = 1 | 高 | 本文即为锚点（原指向的 DEV-STATUS 已补齐） |
| R9 | 电机寿命 / 续航 | 低 | README 待补提示（PRD P2-8） |
| R10 | 官方软件抢 HID | 中 | 代理权检测 + 互斥提示（不做硬杀） |
| R12 | 范围蔓延 | 中 | 变更必走 ADR；PRD §5 边界条款 |
| R13 | 7878 端口与真 DSX 冲突 | 低 | 进行中：当前仅 7878→8787 退让，**占用方识别待做（PRD P2-5）** |

完整登记表（含已消除项 R1/R2/R5/R7/R11）见 `docs/RISK-REGISTER.md`。

### 5.3 文档 ↔ 实现偏差（ARCHITECTURE §7）

> 供改文档时对照；**偏差一律「改文档不改代码」**。

| # | 偏差 | 本次处置 | 验证方式（可复跑） |
|---|---|---|---|
| D1 | TECH-SPEC §6 写「WS 10Hz 合并推送」，实现是逐条转发（仅体感 30Hz 节流） | ⬜ 待改（本次未动 TECH-SPEC） | —— |
| D2 | TECH-SPEC §8 写「四页」，实际十页 + 体验区面板 | ⬜ 待改（本次未动 TECH-SPEC） | —— |
| D3 | TECH-SPEC §1 线程表缺 `fg-watcher` / `dsx-ingress` / `keymonitor` | ⬜ 待补 | —— |
| D4 | `PROTOCOL.md` 引用仓库外 `../../ANALYSIS.md` | ✅ 已改（改为指向 `docs/RESEARCH-HIDDEN-FEATURES.md` / `docs/adr/`，关键结论就地补写） | `git grep -n "ANALYSIS.md" docs/PROTOCOL.md` **应无输出** |
| D5 | RISK-REGISTER R8 指向不存在的 DEV-STATUS | ✅ 已补（本文） | `git ls-files docs/DEV-STATUS.md` 有输出 |
| D6 | ADR-INDEX 只写到 ADR-030 | ✅ 已补 031–034 | `git grep -n "ADR-034" docs/adr/ADR-INDEX.md` 有输出 |
| D7 | README 文档索引缺失 | ✅ 已补 | `git grep -n "docs/PRD.md" README.md` 有输出 |
| D8 | `smoke_test.py` 被 pytest 收集必 ConnectionRefused | ✅ 已加 `backend/conftest.py` 排除 + CI 脚本绕过 | `python -m pytest backend -q` → `35 passed` 且**不再 Interrupted** |

---

## 6. 本地开发与测试跑法

| 目的 | 命令（仓库根执行） | 备注 |
|---|---|---|
| 起服务（无窗口 + Mock） | `python backend/run.py --mock --no-gui` | 无手柄也跑；GUI 版去掉 `--no-gui` |
| 健康检查 | `curl http://127.0.0.1:18765/api/health` | 期望 `{"ok": true, ...}` |
| 改端口（避免单实例冲突） | `python backend/run.py --mock --no-gui --port 18799` | 默认 18765；已有实例会被唤起，CI 用非默认端口 |
| pytest 单测 | `python -m pytest backend -q` | `backend/conftest.py` 已排除 `smoke_test.py`；v0.3.2 规范化后 **35 passed**（改造前 15） |
| 脚本式单测（CI 名单） | `python tools/run_script_tests.py` | 子进程逐个隔离，任一非零即失败 |
| 脚本式单测（含本机专属） | `python tools/run_script_tests.py --local` | 追加 `test_screen_offline`（**需本机安装飞智空间站出厂 bin**） |
| Mock 全链路冒烟 | `python tools/run_smoke.py` | 自动起服务（18799）→ 轮询就绪 → 跑冒烟 → 收尾杀进程 |
| 前端构建 | `cd frontend; npm ci; npm run build` | `tsc -b && vite build` |
| 版本一致性 | `python tools/check_version.py` | 发版前自校验 |

**一次性 / 诊断脚本**统一在 `tools/`（`_maze_check.py`、`_maze_diag.py`、`_smoke_dsu.py`、`_ws_check.py`、
`_patch_sliders.py`）。其中 `_smoke_dsu.py` 依赖 `backend/app/dsu.py`（已带 `sys.path` 兜底），
`_ws_check.py` **需先起服务**（默认连 `127.0.0.1:18765`，**不进 CI**）。

---

## 7. 真机验收记录表（T05 填写）

> **需人工 + 手柄，不进 CI。** 每次规范化改造或写路径改动后重跑一遍，确认「改了文档/配置，行为一点没变」。
> 固件版本从 `/api/state` 的 `device.versions` 读（cmd1 心跳读回）。

### 7.1 记录表

| 日期 | 固件版本 | # | 条目 | 结果 | 备注 |
|---|---|---|---|---|---|
| —— | —— | 1 | 真机连接 + 启动卫生 panic 已执行（事件日志可见） | ⬜ 待测 | TEST-PLAN v0.1 #2 |
| —— | —— | 2 | 实验室 preview 不落账本、apply 落账本 | ⬜ 待测 | TEST-PLAN v0.1 #3 |
| —— | —— | 3 | 账本一致性：应用后重启软件，账本重读 = 手柄实际 | ⬜ 待测 | TEST-PLAN v0.1 #4 |
| —— | —— | 4 | 代理权：开飞智空间站 ≤5s 状态签切换；15s 空闲自动收回并重放 | ⬜ 待测 | TEST-PLAN v0.1 #5/#6 |
| —— | —— | 5 | 退出卫生：托盘退出后手柄无残留效果 | ⬜ 待测 | TEST-PLAN v0.1 #8 |
| —— | —— | 6 | 托盘三态图标正确 | ⬜ 待测 | TEST-PLAN v0.1 #10 |
| —— | —— | 7 | 灯光：进页还原 + 写入驻留（`led_save_flash` 必须做，否则休眠丢失） | ⬜ 待测 | TEST-PLAN v0.3 |
| —— | —— | 8 | 屏幕 GIF 烧写全链路 | ⬜ 待测 | TEST-PLAN v0.1 |
| —— | —— | 9 | 板载宏：写入后**关软件**仍触发 | ⬜ 待测 | TEST-PLAN v0.3 |
| —— | —— | 10 | 拓展键：按 M 键图上 M 键亮 | ⬜ 待测 | TEST-PLAN v0.3 |
| —— | —— | 11 | 体感：DSU 桥在 Yuzu/Cemu 能识别；迷宫倾斜方向正确 | ⬜ 待测 | TEST-PLAN v0.3 |
| —— | —— | 12 | Mod 管家：官方 Mod 端到端收包（PRD P2-2，ADR-025 明载「待真机实测」） | ⬜ 待测 | TEST-PLAN v0.2 |

### 7.2 真机专属待办登记（**需人工，不进 CI**）

| 条目 | 来源 | 状态 |
|---|---|---|
| HID 总线满负荷上限压测（探针压测子命令） | RISK R6 / PRD P1-14 | ⬜ 待做（需人工） |
| 灯表 10 帧容量产品化（≤10 帧 or 写入前显式告警） | PRD P1-13 / §6 Q2 | ⬜ 待真机确认超限行为后决定 |
| XGameMonitor 型 Mod 真机抽测 | PRD P2-2 | ⬜ 待做（需人工） |
| trace 录制（`tools/record_trace.py`，一次即可） | PRD P2-6 / T04.5 | ⬜ 待做（需人工 1 次） |

> 任何一条与改造前行为不一致 → **先** `git reset --hard safe-20261006-pre-standardization`，
> **再**在 7.1 表记录现象，**不要**在真机上边调边试。
