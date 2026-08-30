# Vehicle Diagnosis Agent 🚗🔧

基于 **FastAPI + pgvector RAG + LLM** 的车辆故障诊断智能问答服务，面向售后工程师：输入故障现象或故障码，Agent 自动检索知识库、历史案例与车辆档案，给出结构化的排查建议。

## ✨ 功能特性

- **诊断对话 Agent**：LLM 按需调用 6 个工具（车辆档案、故障码查询、相似案例、知识库检索、配件信息、维修记录），支持多轮会话与上下文记忆
- **RAG 知识库**：文档切片入库 + 向量化（pgvector），混合检索（向量 + 关键词），支持 PDF/Markdown/TXT 上传
- **车辆记忆**：按 VIN 记录历史故障与维修记录，诊断时自动参考
- **Web 聊天界面**：内置开箱即用的聊天页面，无需前端开发即可使用
- **可观测性**：请求链路日志（request id）、`/health` 健康检查、`/metrics` 指标

## 🛠 技术栈

| 层 | 技术 |
|---|---|
| Web 框架 | FastAPI + Uvicorn（Python 3.11） |
| LLM / Agent | LangChain 0.3 + 智谱 GLM（OpenAI 兼容接口，可替换其他兼容服务） |
| 向量检索 | PostgreSQL + pgvector（`embedding-3`，1024 维） |
| ORM | SQLAlchemy 2.0 |
| 部署 | Docker Compose（app + db 两容器） |

## 🚀 快速开始

### 1. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入你的 LLM API Key（默认对接智谱开放平台，任何 OpenAI 兼容服务改 `LLM_BASE_URL` 即可）：

```ini
LLM_MODEL=glm-4-plus
LLM_API_KEY=your-api-key-here
LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
```

### 2. 启动服务（Docker Compose）

```bash
docker compose up -d --build
```

会启动两个容器：

- `vda-db`：PostgreSQL 18 + pgvector（宿主机端口 `5433`）
- `vda-app`：FastAPI 应用（宿主机端口 `8000`），启动时自动建业务表与向量表

### 3. 初始化知识库与演示数据

```bash
# 批量导入 data/documents 下的知识文档（也可不导入，服务照常运行）
docker exec vda-app python scripts/ingest_documents.py --dir data/documents

# 写入演示用的车辆、故障码、案例、配件数据（可选）
docker exec vda-app python scripts/seed_demo_data.py
```

### 4. 开始使用

| 入口 | 地址 |
|---|---|
| Web 聊天界面 | http://localhost:8000/ |
| Swagger 接口文档 | http://localhost:8000/docs |
| 健康检查 | http://localhost:8000/health |

试试问：*“比亚迪汉EV报故障码P0562，怎么排查？”*

## 💻 本地开发（不用容器跑应用）

```bash
# 只启动数据库容器
docker compose up -d db

pip install -r requirements.txt
uvicorn app.main:app --reload
```

运行测试：

```bash
pytest
```

评测脚本（需先启动服务并配置 API Key）：

```bash
python scripts/eval_test.py --base http://localhost:8000
```

## 📡 API 一览

业务接口统一挂在 `/api/v1` 下：

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/chat` | 诊断对话（核心接口） |
| GET | `/api/v1/sessions` | 会话列表 |
| GET | `/api/v1/sessions/{session_id}` | 会话消息详情 |
| POST | `/api/v1/documents` | 上传知识文档 |
| GET | `/api/v1/documents` | 文档列表 |
| DELETE | `/api/v1/documents/{doc_id}` | 删除文档 |
| POST | `/api/v1/search` | 知识库语义检索 |
| GET | `/api/v1/vehicles/{vin}` | 车辆档案与故障历史 |
| GET | `/health` / `/metrics` | 健康检查 / 运行指标 |

## 📁 项目结构

```
vehicle-diagnosis-agent/
├── app/
│   ├── api/routes/      # 路由：diagnosis / knowledge / vehicle / health
│   ├── core/            # Agent 编排、LLM、Embedding、混合检索、提示词
│   ├── db/              # SQLAlchemy 模型与连接
│   ├── memory/          # 车辆记忆
│   ├── rag/             # pgvector 向量存储
│   ├── tools/           # 6 个 Agent 工具（注册表统一装配）
│   ├── web/             # 内置聊天界面（静态页）
│   └── main.py          # 应用入口
├── data/documents/      # 知识库示例文档
├── scripts/             # 文档入库 / 演示数据 / 评测脚本
├── tests/               # pytest 测试
├── init.sql             # 数据库初始化（pgvector + pg_trgm 扩展）
└── docker-compose.yml
```

## ⚠️ 安全说明

- 真实密钥只放本地 `.env`（已被 `.gitignore` 排除，不会提交）；`.env.example` 仅含占位符，作为配置模板
- `docker-compose.yml` 中的数据库密码 `postgres` 仅为本地开发默认值，生产部署请修改并改用密钥管理
