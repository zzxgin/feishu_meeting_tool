# 使用官方 Python 轻量级镜像
FROM registry.cn-hangzhou.aliyuncs.com/aliyuncs/python:3.9-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量，防止 Python 生成 .pyc 文件，并让日志实时输出
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 复制依赖文件
COPY requirements.txt .

# 安装依赖
# --no-cache-dir 减小镜像体积
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 创建 downloads 和 user_token 目录
RUN mkdir -p downloads user_token

# 暴露端口
EXPOSE 29090

# 启动命令 (使用 waitress)
CMD ["python", "listen_recording.py"]
