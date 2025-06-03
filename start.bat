@echo off
chcp 65001 >nul
echo === AI Q&A Assistant 部署脚本 ===
echo.

REM 检查Docker是否安装
docker --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Docker 未安装，请先安装 Docker Desktop
    echo 访问 https://docs.docker.com/desktop/windows/ 获取安装指南
    pause
    exit /b 1
)

REM 检查Docker Compose是否安装
docker-compose --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Docker Compose 未安装，请先安装 Docker Compose
    echo 访问 https://docs.docker.com/compose/install/ 获取安装指南
    pause
    exit /b 1
)

echo ✅ Docker 和 Docker Compose 已安装
echo.

REM 检查API密钥配置
echo 🔍 检查配置...
findstr /C:"AIzaSyCy_1x6sB__B-qGTMCJszIDeJwpDT_hvnc" app.py >nul
if not errorlevel 1 (
    echo ⚠️  警告: 检测到默认API密钥，请配置你的Google API密钥
    echo    编辑 app.py 文件或设置 GOOGLE_API_KEY 环境变量
    echo.
)

REM 构建和启动服务
echo 🚀 启动服务...
docker-compose down >nul 2>&1
docker-compose up -d --build

if errorlevel 1 (
    echo ❌ 服务启动失败，请检查错误信息
    pause
    exit /b 1
)

echo.
echo ✅ 服务启动成功！
echo 📱 访问地址: http://localhost:5000
echo 📊 查看日志: docker-compose logs -f
REM ... (additional lines if any)
