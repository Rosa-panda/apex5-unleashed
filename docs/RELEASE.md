# RELEASE · 发版操作说明（SOP）

> **本文只讲「怎么操作」**。版本号语义、CI 触发条件与产物命名规则写在 `.github/workflows/release.yml`
> 头部注释里；当前版本号与缺陷 backlog 见 `docs/DEV-STATUS.md`。
>
> ⚠ **发布动作需本人拍板**：打 tag / push / 创建 Release 都是对外的不可逆动作，
> 本文**不自动执行**任何一条，只给出可照做的命令清单。

---

## 1. 前置概念（30 秒搞清）

| 概念 | 说明 |
|---|---|
| 版本唯一真相源 | 仓库根 `VERSION`（纯文本，如 `0.3.2`）。界面 `/api/version`、exe 文件属性、Release 全部从它来 |
| tag 必须与 VERSION 一致 | tag = `v${VERSION}`。**不一致 CI 直接失败**（「tag … 与 VERSION 不一致」） |
| 触发方式 | ① push `main`；② push `v*` tag。两条都会跑同一套打包流程 |
| 自动判归 | push main 时：若**远端不存在** `v${VERSION}` tag → 发**正式版**；已存在 → 滚动替换 **nightly** 预发布 |
| 门禁（T03.1 / Q6 严格模式） | `release.yml` 的 `windows` job 声明 `needs: test`——**测试红 = 不打包、不发版**。四道测试见 §2 |
| 复用的测试 workflow | `.github/workflows/ci.yml`（可独立在 push/PR 触发，也可被 release.yml 以 `uses:` 复用） |

---

## 2. 发版前自查（必须全绿）

在仓库根执行，四条与 CI 完全一致（CMake→不，这里是四条命令）：

```powershell
# ① pytest 式单测（smoke_test.py 已由 backend/conftest.py 排除）
python -m pytest backend -q

# ② 脚本式单测（纯 Mock 名单）
python tools/run_script_tests.py

# ③ Mock 全链路冒烟（自动起服务在 18799 → 跑冒烟 → 自动收尾）
python tools/run_smoke.py

# ④ 前端构建
cd frontend; npm ci; npm run build; cd ..

# 附：版本号一致性校验（CI 发版第一步就是这个）
python tools/check_version.py
```

> `--local` 说明：`python tools/run_script_tests.py --local` 会额外跑 `test_screen_offline`
> （依赖本机 `C:\Program Files\Flydigi Space Station\...\default_screen_image_*.bin`），
> **CI 上默认跳过**，本机装了飞智空间站的话建议也跑一遍。

---

## 3. 标准发版流程（推荐）

1. **改版本号**：编辑仓库根 `VERSION`（唯一改动点），例如 `0.3.2` → `0.3.3`。
2. **自检**：跑 §2 四条（全绿才继续）。
3. **提交并推送**（版本控制动作由本人执行）：

   ```powershell
   git add VERSION
   git commit -m "release: v0.3.3"
   git push origin main
   ```

4. **CI 自动完成**：push main 触发 `build-release` → 先跑 `test` job（复用 ci.yml）→ 通过后打包 →
   远端无 `v0.3.3` tag ⇒ 自动发布**正式版** `Apex5Unleashed-0.3.3-win64.zip`。
5. **验收产物**：见 §5。

---

## 4. 手动补发某个版本（例如现在 VERSION=0.3.2 但没有对应 Release）

> 场景：`release.yml` 只在「VERSION bump 且远端无同名 tag」时自动发正式版。
> 若历史上本地改了 VERSION 但没推送过 tag/代码，就会形成「版本号超前于 Release」的断链。

**第 0 步 · 先核实远端现状（必须联网，未核实前不要打 tag）：**

```powershell
git ls-remote --tags origin                       # 看远端已有哪些 tag
gh release list --repo Rosa-panda/apex5-unleashed  # 看已有哪些 Release
```

核对要点：

- 若 **已有** `v0.3.2` tag/Release → 什么都不用做，.VERSION 已经是最新且已发布。
- 若 **没有** `v0.3.2`，且确认当前代码就是想要发的那版 → 走下一步。

**第 1 步 · 打 tag 并推送（tag 必须与 VERSION 完全一致）：**

```powershell
git tag v0.3.2
git push origin v0.3.2
```

> push `v*` tag 会单独触发一次 `build-release`，产出正式版 `Apex5Unleashed-0.3.2-win64.zip`。

**第 2 步 · 观察 CI：**

```powershell
gh run list --workflow build-release --repo Rosa-panda/apex5-unleashed --limit 5
gh run watch <run-id>      # 用上一条拿到的 id
```

**回滚 / 撤销（打 tag 不可逆，只能删后再发）：**

```powershell
git push origin --delete v0.3.2   # 删远端 tag
git tag -d v0.3.2                 # 删本地 tag
gh release delete v0.3.2 --repo Rosa-panda/apex5-unleashed --yes --cleanup-tag
```

---

## 5. 产物校验清单

| # | 校验项 | 期望 |
|---|---|---|
| 1 | Release 资产名 | `Apex5Unleashed-<VERSION>-win64.zip`（正式版）／ `Apex5Unleashed-nightly-win64.zip`（开发版） |
| 2 | 解压即用 | 解压后双击 `Apex5Unleashed.exe` 起得来（**无需 Python / Node**） |
| 3 | 版本号一致 | 界面页脚 `/api/version` 与 `VERSION` 一致；nightly 额外带 `GIT_SHA` 短哈希 |
| 4 | 运行日志 | `%APPDATA%\Apex5Unleashed\apex5.log` 有 `[boot]` 启动记录 |
| 5 | 烟雾验收 | 起 Mock 模式（`python backend/run.py --mock`）跑一遍 `TEST-PLAN.md` v0.1 第 1 条 |
| 6 | 真机回归 | 有条件时跑 `docs/DEV-STATUS.md` §7 真机验收表（**需人工 + 手柄**） |

---

## 6. 常见问题

| 现象 | 原因 / 处置 |
|---|---|
| CI 报「tag x 与 VERSION(y) 不一致」 | tag 名必须等于 `v` + `VERSION` 内容。改 VERSION 或改 tag，两者同步后重发 |
| CI 在 `test` job 红了，没打包 | **这是设计好的严格门禁**。修测试；临时绕过属发布红线，不建议 |
| 打好的 Release 是 nightly 不是正式版 | 该 VERSION 的 tag 已存在于远端 → 滚动替换 nightly。要正式版就 bump `VERSION` |
| nightly 想看来源 commit | 产物内 `GIT_SHA`（CI 在仓库根生成，**已被 .gitignore 忽略**，不入仓库） |
| 本地根目录出现 `dist/`、`build/` | 早期在仓库根跑过 PyInstaller 的残留；已被 `.gitignore` 覆盖，可安全删除 |
