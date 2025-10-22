@echo off
chcp 65001 >nul

REM 安装 pnpm
echo Installing pnpm...
call npm install -g pnpm

REM 设置淘宝镜像源
echo Setting up China mirror...
call pnpm config set registry https://registry.npmmirror.com

REM 安装依赖
echo Installing dependencies...
call pnpm install
call npx playwright install

echo 安装完成，点击回车退出
pause