from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from chat.chat_routes import chat_router
from knowledgebase_server.kb_routes import kb_router
from fastapi.staticfiles import StaticFiles
from configs.setting import MEDIA_DIR

# 创建FastAPI实例
app = FastAPI()

# 允许跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载路由
app.include_router(chat_router)
app.include_router(kb_router)

# 挂载静态文件目录
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")

# 程序主入口
if __name__ == "__main__":
    # 导入unicorn服务器的包
    import uvicorn

    # 运行服务器
    uvicorn.run(app, host="127.0.0.1", port=6605, log_level="info")
