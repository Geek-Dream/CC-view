@echo off
chcp 65001 >nul
title Claude Code 桌面助手

REM 保存用户的项目目录（执行脚本前的当前目录）
set CCVIEW_PROJECT_DIR=%CD%

cd /d "%~dp0"

echo ========================================
echo   Claude Code 桌面助手
echo ========================================
echo.

REM 检查 Python3
python3 --version >nul 2>&1
if errorlevel 1 (
    python --version >nul 2>&1
    if errorlevel 1 (
        echo [错误] 未找到 Python，请先安装 Python 3
        echo 下载地址: https://www.python.org/downloads/
        pause
        exit /b 1
    )
    set PYTHON=python
) else (
    set PYTHON=python3
)

REM Python 版本检查（SDK 需要 >= 3.10）
%PYTHON% -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [错误] Python 版本过低，claude-agent-sdk 需要 Python ^>= 3.10
    echo 请升级 Python 后重试
    pause
    exit /b 1
)

echo [1/5] Python3: OK

REM 检查 PyQt6
%PYTHON% -c "import PyQt6" >nul 2>&1
if errorlevel 1 (
    echo [2/5] PyQt6: 未安装
    echo.
    set /p INSTALL=需要安装 PyQt6，是否安装？[Y/n]:
    if not defined INSTALL set INSTALL=Y
    if /i not "%INSTALL%"=="Y" (
        echo [错误] 需要 PyQt6 才能运行
        pause
        exit /b 1
    )
    echo 正在安装 PyQt6...
    pip install PyQt6
    if errorlevel 1 (
        echo [错误] PyQt6 安装失败，请手动运行: pip install PyQt6
        pause
        exit /b 1
    )
    echo PyQt6 安装完成
) else (
    echo [2/5] PyQt6: 已安装
)

REM 检查 claude-agent-sdk（已打包到项目中）
%PYTHON% -c "import claude_agent_sdk" >nul 2>&1
if errorlevel 1 (
    echo [3/5] claude-agent-sdk: 未安装依赖
    echo 正在安装 SDK 依赖 (anyio, mcp)...
    pip install anyio mcp
    if errorlevel 1 (
        echo [错误] SDK 依赖安装失败，请手动运行: pip install anyio mcp
        pause
        exit /b 1
    )
    echo SDK 依赖安装完成
    echo [3/5] claude-agent-sdk: v0.1.66 (已打包)
) else (
    echo [3/5] claude-agent-sdk: v0.1.66 (已打包)
)

REM 检查 claude CLI（SDK 内部需要）
where claude >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 claude 命令
    echo 请先安装 Claude Code CLI
    echo 下载地址: https://docs.anthropic.com/zh-CN/docs/claude-code/CLI
    pause
    exit /b 1
)
echo [4/5] Claude CLI: OK

echo.
echo ========================================
echo   启动中...
echo ========================================
echo.

%PYTHON% main.py

if errorlevel 1 (
    echo.
    echo 程序异常退出。
)

pause
