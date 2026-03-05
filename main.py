import logging
import os

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from routers import auth, project, settings, images, style_ref, author_presets  # 🔥 引入 images
from db.manager import db

# 确保上传根目录存在
os.makedirs("uploads", exist_ok=True)

app = FastAPI(title="TrinityAI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔥 挂载静态文件
app.mount("/static", StaticFiles(directory="uploads"), name="static")

app.include_router(auth.router)
app.include_router(project.router)
app.include_router(settings.router)
app.include_router(images.router)
app.include_router(style_ref.router)
app.include_router(author_presets.router) # 🔥 挂载

@app.get("/")
def root():
    return {"message": "TrinityEngine System Online"}

# 日志过滤器 (保持你之前的设置)
class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        log_line = record.getMessage()
        ignored_paths = ["/logs", "/state", "/details", "/chapters"]
        for path in ignored_paths:
            if path in log_line: return False
        return True

logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

if __name__ == "__main__":
    print("🚀 TrinityEngine Platform Starting...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)