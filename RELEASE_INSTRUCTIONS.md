# Abaqus Agent v0.1.0 — 发布操作指令（给龙虾）

## Context

`abaqus_agent` 项目代码已全部完成，包括：
- 7 阶段 FEA 管线、MCP 架构、5 个 Premium 功能、Web 前端、API
- 打包配置 `pyproject.toml`（hatchling 构建，包名 `abaqus-agent`，版本 `0.1.0`）
- CI/CD：`ci.yml`（测试 + lint）、`publish.yml`（tag 触发自动发 PyPI）
- Docker、Makefile、社区模板、CHANGELOG、CONTRIBUTING 全部就位
- 本地已有 `v0.1.0` tag

**当前状态**：代码在 `main` 分支（remote），本地在 `claude/research-llm-simulation-3a3GX` 分支。所有代码文件已提交，工作区干净。

**目标**：将项目正式发布到 GitHub + PyPI，让用户可以 `pip install abaqus-agent`。

---

## 龙虾操作清单

### Step 1: 本地验证（先确认代码没问题）

```bash
cd /home/user/abaqus_agent

# 切到 main 分支
git checkout main || git checkout master

# 安装依赖
pip install -e ".[dev,mcp]"

# 跑测试
pytest tests/ -v

# 跑 lint
ruff check .

# 试构建包
pip install build
python -m build

# 确认 dist/ 下有 .whl 和 .tar.gz
ls dist/
```

**检查点**：测试全通过、lint 无报错、dist/ 下有两个文件。如果有失败，先修再继续。

---

### Step 2: 确认 GitHub 仓库设置

在浏览器打开 https://github.com/Tomsabay/abaqus_agent 或用 `gh` CLI：

```bash
# 确认仓库存在且可推送
gh repo view Tomsabay/abaqus_agent

# 设置仓库描述和话题标签
gh repo edit Tomsabay/abaqus_agent \
  --description "LLM-powered automation agent for Abaqus FEA — natural language to simulation results" \
  --add-topic abaqus,fea,simulation,llm,automation,mcp,fastapi,python
```

---

### Step 3: 配置 PyPI Trusted Publisher（关键步骤！）

**这一步必须在 PyPI 网站上手动操作，龙虾无法自动完成，需要人工操作。**

1. 登录 https://pypi.org/manage/account/publishing/
2. 点击 "Add a new pending publisher"
3. 填写：
   - PyPI Project Name: `abaqus-agent`
   - Owner: `Tomsabay`
   - Repository name: `abaqus_agent`
   - Workflow name: `publish.yml`
   - Environment name: 留空
4. 提交

**为什么**：`publish.yml` 使用 OIDC trusted publisher（无需 API token），但必须先在 PyPI 注册这个仓库的发布权限。

> **如果你（Tom）还没有 PyPI 账号**：先去 https://pypi.org/account/register/ 注册一个，开启 2FA。

---

### Step 4: 确认 main 分支代码最新

```bash
# 确保 main 分支包含所有最新提交
git checkout main

# 查看 main 是否已包含所有功能代码
git log --oneline -5

# 如果 main 分支落后于 claude/* 分支，需要合并：
git merge claude/research-llm-simulation-3a3GX --no-edit

# 推送到 GitHub
git push origin main
```

---

### Step 5: 推送 v0.1.0 Tag 触发 PyPI 发布

```bash
# 确认 tag 存在
git tag -l

# 如果 v0.1.0 tag 已存在但指向旧 commit，需要重建：
git tag -d v0.1.0
git tag -a v0.1.0 -m "Release v0.1.0 — LLM-powered Abaqus FEA automation"

# 推送 tag 到 GitHub（这会触发 publish.yml 自动发布到 PyPI）
git push origin v0.1.0
```

**检查点**：推送后去 GitHub Actions 页面确认 `Publish to PyPI` workflow 运行成功。

```bash
# 用 CLI 查看 workflow 状态
gh run list --workflow=publish.yml --limit=1
# 等几分钟，查看详情
gh run view <run-id>
```

---

### Step 6: 验证 PyPI 发布成功

```bash
# 等 5 分钟后检查
pip install abaqus-agent==0.1.0

# 验证安装成功
abaqus-agent --help 2>/dev/null || python -c "import server; print('OK')"

# 查看 PyPI 页面
# https://pypi.org/project/abaqus-agent/
```

---

### Step 7: 创建 GitHub Release

```bash
gh release create v0.1.0 \
  --title "v0.1.0 — LLM-Powered Abaqus FEA Automation" \
  --notes "$(cat <<'EOF'
## Highlights

First public release of **abaqus-agent** — an LLM-powered automation agent for Abaqus FEA simulations.

### Features
- **7-stage pipeline**: validate → build → syntaxcheck → submit → monitor → extract → compare
- **MCP server** + HTTP bridge for AI agent integration
- **FastAPI REST API** with SSE streaming for real-time progress
- **Web frontend** with dark theme, YAML editor, KPI charts, live logs
- **LLM planning**: Anthropic Claude, OpenAI GPT, or template fallback
- **4 benchmark cases**: cantilever beam, plate with hole, modal analysis, explicit impact
- **Safety**: AST-based static guard + schema validation + Abaqus syntaxcheck gate
- **5 premium features**: parametric sweeps, mesh adaptivity, multi-physics coupling, extended geometry, auto-repair

### Install
\`\`\`bash
pip install abaqus-agent          # core
pip install abaqus-agent[llm]     # + LLM backends
pip install abaqus-agent[mcp]     # + MCP server
pip install abaqus-agent[all]     # everything
\`\`\`

### Quick Start
\`\`\`bash
abaqus-agent                      # start web server on port 8000
pytest tests/ -v                  # run test suite
python run_benchmark.py --dry-run # validate benchmark specs
\`\`\`
EOF
)" \
  --latest \
  dist/*
```

这条命令会：
- 创建 GitHub Release 页面
- 附带构建产物（.whl 和 .tar.gz）
- 标记为最新版本

---

### Step 8: 验证一切正常

```bash
# 1. PyPI 页面可访问
# https://pypi.org/project/abaqus-agent/0.1.0/

# 2. GitHub Release 页面可访问
gh release view v0.1.0

# 3. pip install 可用
pip install abaqus-agent --upgrade

# 4. CI 绿色
gh run list --workflow=ci.yml --limit=1

# 5. Docker 构建可用（可选）
docker build -t abaqus-agent .
docker run --rm -p 8000:8000 abaqus-agent
```

---

## 故障排除

| 问题 | 解决方案 |
|------|---------|
| `publish.yml` 失败报 "trusted publisher not found" | Step 3 没做或填错了，去 PyPI 重新配置 |
| `publish.yml` 失败报 "project already exists" | 包名被占用，需改 `pyproject.toml` 中的 `name` |
| `pytest` 有测试失败 | 先修测试再发布，不要带着失败发布 |
| `ruff check` 报错 | `ruff check . --fix` 自动修复，然后重新 commit |
| `git push origin v0.1.0` 被拒 | 检查是否有 branch protection rules，或 token 权限不足 |
| Docker build 失败 | 检查 `requirements.txt` 和 `Dockerfile`，确保依赖版本正确 |

---

## 文件路径参考

| 文件 | 用途 |
|------|------|
| `/home/user/abaqus_agent/pyproject.toml` | 包名、版本、依赖 |
| `/home/user/abaqus_agent/.github/workflows/publish.yml` | PyPI 自动发布 |
| `/home/user/abaqus_agent/.github/workflows/ci.yml` | 测试 + lint |
| `/home/user/abaqus_agent/CHANGELOG.md` | 版本日志 |
| `/home/user/abaqus_agent/Dockerfile` | Docker 构建 |
| `/home/user/abaqus_agent/Makefile` | 快捷命令 |
| `/home/user/abaqus_agent/server.py` | CLI 入口 `abaqus-agent` |

---

## 总结：龙虾最小操作路径

如果一切顺利，核心操作就 4 步：

1. `pytest tests/ -v && ruff check .` — 验证代码
2. **人工去 PyPI 配 Trusted Publisher**（Step 3）
3. `git push origin main && git push origin v0.1.0` — 触发发布
4. `gh release create v0.1.0 ...` — 创建 GitHub Release

其他都是验证和善后。
