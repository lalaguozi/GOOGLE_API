#!/bin/bash

# AI Q&A Assistant 启动脚本

echo "=== AI Q&A Assistant 部署脚本 ==="
echo

# 检查Docker是否安装
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装，请先安装 Docker"
    echo "访问 https://docs.docker.com/get-docker/ 获取安装指南"
    exit 1
fi

# 检查Docker Compose是否安装
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose 未安装，请先安装 Docker Compose"
    echo "访问 https://docs.docker.com/compose/install/ 获取安装指南"
    exit 1
fi

echo "✅ Docker 和 Docker Compose 已安装"
echo

# 检查API密钥配置
echo "🔍 检查配置..."
if grep -q "AIzaSyCy_1x6sB__B-qGTMCJszIDeJwpDT_hvnc" app.py; then
    echo "⚠️  警告: 检测到默认API密钥，请配置你的Google API密钥"
    echo "   编辑 app.py 文件或设置 GOOGLE_API_KEY 环境变量"
    echo
fi

# 构建和启动服务
echo "🚀 启动服务..."
docker-compose down 2>/dev/null
docker-compose up -d --build

if [ $? -eq 0 ]; then
    echo
    echo "✅ 服务启动成功！"
    echo "📱 访问地址: http://localhost:5000"
    echo "📊 查看日志: docker-compose logs -f"
    echo "🛑 停止服务: docker-compose down"
    echo
    echo "🌐 如果需要外网访问，请:"
    echo "   1. 配置防火墙开放5000端口"
    echo "   2. 使用服务器公网IP:5000访问"
else
    echo "❌ 服务启动失败，请检查错误信息"
    exit 1
fi
