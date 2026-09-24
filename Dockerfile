# ---------- 前端构建 ----------
FROM node:20-alpine AS frontend
# 国内服务器构建可换成 https://registry.npmmirror.com
ARG NPM_REGISTRY=https://registry.npmjs.org
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm config set registry $NPM_REGISTRY && npm install --no-fund --no-audit
COPY frontend/ ./
RUN npm run build

# ---------- 后端运行 ----------
FROM python:3.12-slim
WORKDIR /app

# 国内服务器构建可换成 https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_INDEX=https://pypi.org/simple

# onnxruntime/opencv 需要 libgomp / libglib
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -i $PIP_INDEX -r requirements.txt

COPY backend/ ./backend/
COPY --from=frontend /build/dist ./frontend/dist

ENV TZ=Asia/Shanghai
VOLUME ["/app/backend/data"]
EXPOSE 8000

WORKDIR /app/backend
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
