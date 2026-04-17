@echo off
chcp 65001 >nul
title Claude Code 桌面助手

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

echo [1/3] Python3: OK

REM 检查 PyQt6
%PYTHON% -c "import PyQt6" >nul 2>&1
if errorlevel 1 (
    echo [2/3] PyQt6: 未安装
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
    echo [2/3] PyQt6: 已安装
)

REM 检查 claude CLI
where claude >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 claude 命令
    echo 请先安装 Claude Code CLI
    echo 下载地址: https://docs.anthropic.com/zh-CN/docs/claude-code/CLI
    pause
    exit /b 1
)
echo [3/3] Claude CLI: OK

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
