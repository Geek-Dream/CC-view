#!/bin/bash
# Claude Code 桌面助手 — macOS / Linux 启动脚本
# 用法: ./run.sh

# 保存用户的项目目录（执行脚本前的当前目录）
export CCVIEW_PROJECT_DIR="$PWD"

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "========================================"
echo "  Claude Code 桌面助手"
echo "========================================"
echo ""

# 检测是否在终端中运行
IN_TERMINAL() {
    if [ -t 0 ] || [ -z "$TERM_SESSION_ID" -a "$DISPLAY" != "" ]; then
        return 0
    fi
    if [ -n "$TERM_PROGRAM" ]; then
        return 0
    fi
    return 1
}

# 不在终端中则打开一个新终端窗口
if ! IN_TERMINAL; then
    echo "[提示] 将打开终端窗口来显示日志..."
    osascript -e "tell app \"Terminal\" to do script \"cd $(printf '%q' "$DIR") && ./run.sh && exit\"" 2>/dev/null
    exit 0
fi

# ===== 以下在终端中运行 =====

# 寻找 >= 3.10 的 Python（SDK 需要 3.10+）
find_python() {
    for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
        if command -v "$candidate" &> /dev/null; then
            ver=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
            major=$("$candidate" -c "import sys; print(sys.version_info.major)" 2>/dev/null)
            minor=$("$candidate" -c "import sys; print(sys.version_info.minor)" 2>/dev/null)
            if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
                echo "$candidate"
                return 0
            fi
        fi
    done
    echo ""
    return 1
}

PYTHON_CMD=$(find_python)
if [ -z "$PYTHON_CMD" ]; then
    echo "[错误] 未找到 Python >= 3.10，claude-agent-sdk 需要 Python 3.10+"
    echo "请安装: brew install python@3.11"
    echo ""
    read -p "按回车键退出..." REPLY
    exit 1
fi

PYTHON_VER=$("$PYTHON_CMD" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "[1/5] Python3: $PYTHON_VER ($PYTHON_CMD)"

# 检查 PyQt6
if ! "$PYTHON_CMD" -c "import PyQt6" 2>/dev/null; then
    echo "[2/5] PyQt6: 未安装"
    echo ""
    read -p "需要安装 PyQt6，是否安装？[Y/n] " REPLY
    REPLY="${REPLY:-Y}"
    if [[ "$REPLY" =~ ^[Yy]$ ]]; then
        echo "正在安装 PyQt6..."
        "$PYTHON_CMD" -m pip install PyQt6
        if [ $? -ne 0 ]; then
            echo "[错误] PyQt6 安装失败，请手动运行: pip3 install PyQt6"
            echo ""
            read -p "按回车键退出..." REPLY
            exit 1
        fi
        echo "PyQt6 安装完成"
    else
        echo "[错误] 需要 PyQt6 才能运行"
        read -p "按回车键退出..." REPLY
        exit 1
    fi
else
    echo "[2/5] PyQt6: 已安装"
fi

# 检查 claude-agent-sdk（已打包到项目中）
if ! "$PYTHON_CMD" -c "import claude_agent_sdk" 2>/dev/null; then
    echo "[3/5] claude-agent-sdk: 未安装依赖"
    echo "正在安装 SDK 依赖 (anyio, mcp)..."
    "$PYTHON_CMD" -m pip install anyio mcp
    if [ $? -ne 0 ]; then
        echo "[错误] SDK 依赖安装失败，请手动运行: pip3 install anyio mcp"
        echo ""
        read -p "按回车键退出..." REPLY
        exit 1
    fi
    echo "SDK 依赖安装完成"
    echo "[3/5] claude-agent-sdk: v0.1.66 (已打包)"
else
    echo "[3/5] claude-agent-sdk: v0.1.66 (已打包)"
fi

# 检查 claude CLI（SDK 内部需要）
if ! command -v claude &> /dev/null; then
    echo "[错误] 未找到 claude 命令"
    echo "请先安装 Claude Code CLI"
    echo "下载地址: https://docs.anthropic.com/zh-CN/docs/claude-code/CLI"
    echo ""
    read -p "按回车键退出..." REPLY
    exit 1
fi
echo "[4/5] Claude CLI: $(claude --version 2>&1 | head -1)"

echo ""
echo "========================================"
echo "  启动中...（关闭界面后按 Ctrl+C 退出）"
echo "========================================"
echo ""

"$PYTHON_CMD" main.py
