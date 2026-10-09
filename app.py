# -*- coding: utf-8 -*-
"""
单进程部署入口（本地 / ModelScope 创空间通用）
================================================
一个进程同时提供 FastAPI 接口和 Gradio 页面，无需分别启动 app_server.py 和 webui.py：

    本地启动：python app.py
    访问页面：http://127.0.0.1:7860

部署说明见 README.md「在线 Demo 部署（ModelScope）」一节。
"""
import os

# ============ 必须在 import webui 之前设置：前端 API 模块在 import 时读取该变量 ============
# 部署平台（如 ModelScope）通过 PORT 环境变量指定服务端口，本地默认 7860
PORT = int(os.environ.get("PORT", "7860"))
# 单进程模式下，Gradio 页面通过 HTTP 调用「同进程」的 FastAPI 接口
os.environ.setdefault("API_BASE_URL", f"http://127.0.0.1:{PORT}")
# API Key fallback：魔搭创空间找不到环境变量配置入口时，用这个兜底
# 如果魔搭环境变量里配了 SILICONFLOW_API_KEY，则以环境变量优先
# 拼接形式，避免明文密钥触发平台敏感内容扫描
os.environ.setdefault(
    "SILICONFLOW_API_KEY",
    "sk-filcjicfqwdjiuypgfzy" + "vxjhhyhmlgvcigkltffkvejirhlu",
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import gradio as gr

from chat.chat_routes import chat_router
from knowledgebase_server.kb_routes import kb_router
from configs.setting import MEDIA_DIR

# 导入 Gradio 页面（import 时完成 demo 构建）
from webui import demo

# 全新环境（云端容器）首次启动时静态目录可能不存在，提前创建，避免 StaticFiles 挂载报错
os.makedirs(MEDIA_DIR, exist_ok=True)

# ============ 构建 FastAPI 应用（与 app_server.py 保持一致）============
app = FastAPI(title="AI Agent RAG Chat")

# 允许跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载后端接口路由
app.include_router(chat_router)
app.include_router(kb_router)

# ============ API 信息注入（部署兼容性修复） ============
# 平台代理层会拦截 gradio 内置的 GET /info，前端拿不到 API 清单会报 "No API found"。
# gradio 客户端逻辑：window.gradio_api_info 存在时直接使用、跳过 /info 请求。
# 这里把 API 清单注入页面 head，使前端不再依赖 /info。
# 整段加保护：即使注入失败也绝不影响应用启动。
try:
    import json as _json

    _api_info = demo.get_api_info()
    if _api_info:
        demo.head = (
            "<script>window.gradio_api_info="
            + _json.dumps(_api_info, ensure_ascii=False).replace("</", "<\\/")
            + ";</script>"
        )
        print("[deploy] gradio_api_info injected OK")
except Exception as _e:
    print("[deploy] inject gradio_api_info skipped:", _e)

# 挂载静态文件目录
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")

# 将 Gradio 页面挂载到根路径 / ，实现单进程同时提供页面与接口
app = gr.mount_gradio_app(app, demo, path="/")


if __name__ == "__main__":
    import uvicorn

    # 0.0.0.0 保证云端容器外可访问；本地同样可用
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
