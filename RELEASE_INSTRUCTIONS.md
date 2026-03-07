# Abaqus Agent v0.1.0 — 发布操作指令（给龙虾）

## Context

`abaqus_agent` 项目代码已全部完成，包括：
- 7 阶段 FEA 管线、MCP 架构、5 个 Premium 功能、Web 前端、API
- CI/CD：`ci.yml`（测试 + lint）
- Docker、Makefile、社区模板、CHANGELOG、CONTRIBUTING 全部就位
- 本地已有 `v0.1.0` tag

**当前状态**：代码在 `main` 分支（remote），本地在 `claude/research-llm-simulation-3a3GX` 分支。所有代码文件已提交，工作区干净。

**目标**：将项目正式发布到 GitHub，创建 Release，让别人能找到和使用这个项目。

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
```

**检查点**：测试全通过、lint 无报错。如果有失败，先修再继续。

---

### Step 2: 设置 GitHub 仓库描述和 Topics

```bash
# 设置仓库描述
gh repo edit Tomsabay/abaqus_agent \
  --description "LLM-powered automation agent for Abaqus FEA — Natural language → CAE model → Solver → KPI report"

# 添加话题标签（让别人搜 abaqus topic 时能找到）
gh repo edit Tomsabay/abaqus_agent \
  --add-topic abaqus,llm,abaqus-python-script,finite-element-analysis,ai-agent,cae,fea
```

如果 `gh` 没有装，也可以手动操作：
1. 打开 https://github.com/Tomsabay/abaqus_agent/settings
2. 在 "About" 区域填写 Description
3. 在 "Topics" 区域添加标签

---

### Step 3: 截取 Dashboard 截图（提升 README 视觉冲击力）

```bash
# 1. 启动服务
python server.py

# 2. 浏览器打开 http://localhost:8000

# 3. 加载 cantilever case，跑一遍流水线

# 4. 截图（推荐包含：深色主题 + YAML 编辑器 + KPI 图表 + 实时日志）
#    - macOS: Cmd+Shift+4
#    - Windows: Win+Shift+S
#    - 如果要录 GIF：用 LICEcap、Kap 或 gifcap

# 5. 保存截图到 docs/assets/dashboard.png

# 6. 更新 README.md，把 ASCII 示意图替换为：
#    ![Dashboard](docs/assets/dashboard.png)
#
#    找到 README 中 "## Dashboard Preview" 部分，
#    删掉 ASCII 框图和 HTML 注释，替换为上面的图片引用
```

---

### Step 4: 确认 main 分支代码最新

```bash
# 确保 main 分支包含所有最新提交
git checkout main

# 查看 main 是否已包含所有功能代码
git log --oneline -5

# 如果 main 分支落后于 claude/* 分支，需要合并：
git merge claude/research-llm-simulation-3a3GX --no-edit

# 提交截图（如果 Step 3 做了的话）
git add docs/assets/dashboard.png README.md
git commit -m "docs: add dashboard screenshot to README"

# 推送到 GitHub
git push origin main
```

---

### Step 5: 创建并推送 v0.1.0 Tag

```bash
# 确认 tag 状态
git tag -l

# 如果 v0.1.0 tag 已存在但指向旧 commit，需要重建：
git tag -d v0.1.0
git tag -a v0.1.0 -m "Release v0.1.0 — LLM-powered Abaqus FEA automation"

# 推送 tag 到 GitHub
git push origin v0.1.0
```

---

### Step 6: 创建 GitHub Release

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

### Install from source
```bash
git clone https://github.com/Tomsabay/abaqus_agent.git
cd abaqus_agent
pip install -e ".[all]"
abaqus-agent  # start web server on port 8000
```

### Docker
```bash
docker compose up -d
# API at http://localhost:8000
```
EOF
)" \
  --latest
```

---

### Step 7: 验证一切正常

```bash
# 1. GitHub Release 页面可访问
gh release view v0.1.0

# 2. CI 绿色
gh run list --workflow=ci.yml --limit=1

# 3. 仓库描述和 Topics 正确显示
gh repo view Tomsabay/abaqus_agent

# 4. Docker 构建可用（可选）
docker build -t abaqus-agent .
docker run --rm -p 8000:8000 abaqus-agent
```

---

## 故障排除

| 问题 | 解决方案 |
|------|---------|
| `pytest` 有测试失败 | 先修测试再发布，不要带着失败发布 |
| `ruff check` 报错 | `ruff check . --fix` 自动修复，然后重新 commit |
| `git push origin main` 被拒 | 检查 token 权限，或先 `git pull origin main --rebase` |
| `gh` 命令不存在 | `brew install gh`（macOS）或 `apt install gh`（Ubuntu） |
| `gh release create` 报错 "tag already exists" | tag 已推但没建 release，去掉 tag 参数直接建 |
| Docker build 失败 | 检查 `requirements.txt` 和 `Dockerfile`，确保依赖版本正确 |

---

## 总结：龙虾最小操作路径

如果一切顺利，核心操作就 4 步：

1. `pytest tests/ -v && ruff check .` — 验证代码
2. `gh repo edit ...` — 设置仓库描述和 Topics
3. `git push origin main && git push origin v0.1.0` — 推送代码和 tag
4. `gh release create v0.1.0 ...` — 创建 GitHub Release

截图是加分项，有时间就做，没时间先跳过（README 里有 ASCII 示意图兜底）。
