# 使用Python 3.9官方镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 复制requirements文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 5000

# 设置环境变量
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

# 启动应用
CMD ["python", "app.py"]
