# AI Agent Demo

基于 LangGraph + Vue 3 的 AI Agent 应用，支持工具调用、流式响应和多 LLM 提供商切换。

## 架构概览

```
┌──────────────┐     SSE      ┌──────────────┐    HTTP     ┌──────────────┐
│   Frontend   │ ◄──────────► │    Nginx     │ ◄─────────► │   Backend    │
│   Vue 3 SPA  │   /chat      │  反向代理    │   /chat     │  FastAPI     │
│   :8080      │              │   :80        │             │  + LangGraph │
└──────────────┘              └──────────────┘             │  :8000       │
                                                           └──────┬───────┘
                                                                  │
                                                           ┌──────▼───────┐
                                                           │    Redis     │
                                                           │   :6379      │
                                                           └──────────────┘
```

## 功能特性

- **LangGraph Agent**：基于状态图的多工具调用 Agent，支持任务增删查
- **流式响应**：SSE 协议实时推送 LLM 生成内容、工具调用状态
- **多 LLM 提供商**：支持 Qwen (通义千问) / OpenAI / Anthropic 一键切换
- **LangSmith 集成**：所有 Agent 运行自动追踪，可视化查看每步输入输出
- **容器化部署**：Podman Compose 一键启动，前后端 + Redis 全容器化
- **状态持久化**：SQLite Checkpoint 保存 Agent 对话状态，容器重启不丢失

## 项目结构

```
.
├── podman-compose.yml        # 容器编排
├── .env                      # 环境变量（密钥，不提交 Git）
├── .gitignore
├── .dockerignore
├── backend/
│   ├── Containerfile         # 后端容器镜像
│   ├── requirements.txt      # Python 依赖
│   ├── .env                  # 本地开发环境变量
│   ├── .dockerignore
│   └── app/
│       ├── main.py           # FastAPI 入口，SSE 流式接口
│       └── agent_config.py   # LangGraph Agent 定义（状态、工具、图）
└── fronted/
    ├── Containerfile         # 前端容器镜像（多阶段构建）
    ├── nginx.conf            # Nginx 配置（SPA 路由 + API 反向代理）
    ├── package.json          # Node.js 依赖
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── App.vue
        ├── main.js
        ├── style.css
        └── components/
            └── ChatWindow.vue  # 聊天窗口组件（SSE 流解析 + 工具状态展示）
```

## 快速开始

### 前置条件

- [Podman](https://podman.io/) >= 4.0
- [podman-compose](https://github.com/containers/podman-compose) >= 1.0

### 1. 配置环境变量

复制并编辑根目录 `.env` 文件，填入你的 API Key：

```bash
# LLM 提供商选择: qwen / openai / anthropic
LLM_PROVIDER=qwen

# Qwen (通义千问) 配置
DASHSCOPE_API_KEY=你的密钥
QWEN_MODEL=qwen-plus
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# OpenAI 配置（LLM_PROVIDER=openai 时生效）
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o
OPENAI_BASE_URL=https://api.openai.com/v1

# Anthropic 配置（LLM_PROVIDER=anthropic 时生效）
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-opus-4-6
ANTHROPIC_BASE_URL=

# LangSmith 可观测性
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=你的LangSmith密钥
LANGSMITH_PROJECT=ai-agent-project
```

### 2. 一键启动

```bash
podman-compose up -d --build
```

### 3. 访问

| 服务 | 地址 |
|------|------|
| 前端聊天界面 | http://localhost:8080 |
| 后端 API 文档 | http://localhost:8000/docs |
| Redis | localhost:6379 |

### 4. 常用命令

```bash
# 查看运行状态
podman-compose ps

# 查看日志
podman-compose logs -f

# 停止所有服务
podman-compose down

# 停止并清除数据卷
podman-compose down -v

# 重建某个服务（代码变更后）
podman-compose up -d --build backend
```

## 本地开发

### 后端

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
cd fronted
npm install
npm run dev
```

> **注意**：本地开发时，前端默认请求 `http://localhost:8000/chat`。容器部署时由 Nginx 反向代理处理，前端改为请求 `/chat`。

## Agent 工具说明

Agent 内置了 3 个任务管理工具：

| 工具 | 功能 | 参数 |
|------|------|------|
| `add_task` | 添加新任务 | `description` (必填), `due_date` (默认"今天") |
| `list_tasks` | 列出任务 | `status`: all / pending / completed |
| `complete_task` | 标记任务完成 | `task_id` |

## 切换 LLM 提供商

只需修改 `.env` 中的 `LLM_PROVIDER` 值，然后重启：

```bash
# 切换到 OpenAI
LLM_PROVIDER=openai podman-compose up -d

# 切换到 Anthropic
LLM_PROVIDER=anthropic podman-compose up -d
```

## LangSmith 追踪

设置 `LANGSMITH_TRACING=true` 后，所有 Agent 运行会自动记录到 [LangSmith](https://smith.langchain.com)：

- 每个 LLM 调用的输入/输出/耗时
- 工具调用的参数和返回结果
- Agent 的完整状态流转

在 LangSmith Dashboard 中查看项目 `ai-agent-project` 即可。

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | Vue 3 + Vite |
| 反向代理 | Nginx (Alpine) |
| 后端 | FastAPI + Uvicorn |
| Agent 框架 | LangGraph + LangChain |
| LLM | Qwen / OpenAI / Anthropic (可切换) |
| 可观测性 | LangSmith |
| 缓存 | Redis 7 |
| 容器 | Podman + podman-compose |

## License

MIT
