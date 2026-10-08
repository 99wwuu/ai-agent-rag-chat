# AI 智能体知识库问答系统

基于 **LangChain + FastAPI** 的 AI 智能体对话系统，支持 ReAct Agent 自主工具调用、RAG 知识库混合检索与流式输出。

## 功能特性

- 🤖 **ReAct Agent**：大模型根据问题自主决策调用工具（天气查询、网络搜索、代码执行、知识库检索、计算器等）
- 📚 **RAG 知识库**：文档上传后自动切块、向量化并持久化存储，支持基于私有文档的问答
- 🔀 **混合检索**：FAISS 语义检索 + BM25 关键词检索加权融合，jieba 中文分词，召回更全面
- 💬 **流式输出**：基于 asyncio 的异步流式响应，打字机效果逐字返回
- 📎 **临时文档问答**：上传文件无需建库，可直接作为上下文提问
- 🛡️ **健壮性设计**：超时/异常统一兜底，保证流式响应不中断

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Gradio（聊天页 + 知识库管理页） |
| 后端框架 | FastAPI + Uvicorn |
| Agent 框架 | LangChain（create_react_agent / AgentExecutor） |
| 大模型 | Qwen2.5-72B-Instruct（硅基流动 OpenAI 兼容接口） |
| 向量检索 | FAISS + bge-large-zh Embedding |
| 关键词检索 | BM25 + jieba 分词（EnsembleRetriever 加权融合） |
| 数据存储 | SQLite + SQLAlchemy（知识库台账） |
| 异步机制 | asyncio（Queue / Event / create_task / StreamingResponse） |

## 系统架构

```
Gradio 页面（聊天 / 知识库管理）
        │
FastAPI 接口层（/chat/agent_chat、/knowledgebase/*）
        │
LangChain ReAct Agent（Qwen2.5 + 工具集）
        │
   ┌────┴─────────────┐
工具调用（天气/搜索/    RAG 检索层
代码执行/计算器）      FAISS 语义检索 + BM25 关键词检索
        │              EnsembleRetriever 加权融合
        └────┬─────────┘
             ▼
   SQLite（知识库台账）+ 本地文件（FAISS 向量库、文档）
```

## 快速开始

### 方式一：本地开发（前后端分离启动）

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API Key（硅基流动），设置环境变量
#    Windows PowerShell:
setx SILICONFLOW_API_KEY "你的API Key"

# 3. 启动后端服务
python app_server.py
# 接口文档：http://127.0.0.1:6605/docs

# 4. 启动前端页面
python webui.py
```

### 方式二：单进程启动（一键运行 / 部署用）

后端接口与 Gradio 页面合并在一个进程、一个端口，无需开两个终端：

```bash
pip install -r requirements.txt
setx SILICONFLOW_API_KEY "你的API Key"
python app.py
# 页面与接口都在：http://127.0.0.1:7860 （接口文档 /docs）
```

## 在线 Demo 部署（ModelScope 创空间，免费）

1. 注册并登录 [modelscope.cn](https://www.modelscope.cn)，完成实名认证；进入「我的创空间」→「创建创空间」，SDK 选择 **Gradio**，空间可见性选「公开」。
2. 按页面提示克隆创空间 Git 仓库，把本项目全部文件复制进去（保证 `app.py` 在仓库根目录），提交推送：

   ```bash
   git add .
   git commit -m "deploy: ModelScope 创空间在线 Demo"
   git push
   ```

3. 在创空间「设置 → 环境变量」中添加密钥：`SILICONFLOW_API_KEY` = 你的硅基流动 Key（选 Secret 类型，不会公开）。
4. push 后平台自动构建部署，等待几分钟即可获得公开访问链接：`https://www.modelscope.cn/studios/<你的用户名>/<空间名>`，任何人点开都能直接试用。

> 说明：`app.py` 为部署入口，通过 `gr.mount_gradio_app` 把 Gradio 页面挂载到 FastAPI 根路径，单进程同时提供页面与 `/chat`、`/knowledgebase` 接口；端口自动读取平台的 `PORT` 环境变量（本地默认 7860）。免费 CPU 实例的磁盘是临时的，重启后上传的知识库会清空，仅用于演示。

## 量化评测

`eval/` 目录包含检索与生成性能的量化评测脚本（简历中 90% Top-3 命中率的原始证据）：

```bash
python eval/run_eval.py        # 跑 20 题对比 FAISS / BM25 / 混合检索，结果写入 eval/report.json
```

## 核心流程

**RAG 文档入库**：加载文档（txt/pdf/csv/md）→ 文本切块（chunk_size=128，overlap=20）→ Embedding 向量化 → 存入 FAISS 持久化

**Agent 对话**：用户提问 → ReAct 循环（Thought → Action → Observation）自主选择工具/知识库 → 检索结果拼入 Prompt → 流式生成回答

## 项目亮点

- **混合检索策略**：针对 FAISS 语义检索精确匹配弱、BM25 不懂同义词的问题，使用 EnsembleRetriever 按 0.5/0.5 权重融合，显著提升召回率
- **异步流式架构**：Agent 后台任务执行，主循环通过 asyncio.wait 竞速监听 token 队列、结束信号与任务状态，配合自定义 Callback 实现稳定的流式输出
- **可扩展工具设计**：工具基于统一接口封装，可快速扩展（如新增计算器工具，并针对 eval 设计了字符白名单 + 禁用内置函数的双层安全防护）
- **密钥安全管理**：API Key 通过环境变量注入，配合 .gitignore 避免凭据泄露
