#!/bin/bash
# Claude Code 桌面助手 — macOS / Linux 启动脚本
# 用法: ./run.sh

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

# 检查 Python3
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未找到 python3，请先安装 Python 3"
    echo "下载地址: https://www.python.org/downloads/"
    echo ""
    read -p "按回车键退出..." REPLY
    exit 1
fi
echo "[1/3] Python3: $(python3 --version 2>&1)"

# 检查 PyQt6
if ! python3 -c "import PyQt6" 2>/dev/null; then
    echo "[2/3] PyQt6: 未安装"
    echo ""
    read -p "需要安装 PyQt6，是否安装？[Y/n] " REPLY
    REPLY="${REPLY:-Y}"
    if [[ "$REPLY" =~ ^[Yy]$ ]]; then
        echo "正在安装 PyQt6..."
        pip3 install PyQt6
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
    echo "[2/3] PyQt6: 已安装"
fi

# 检查 claude CLI
if ! command -v claude &> /dev/null; then
    echo "[错误] 未找到 claude 命令"
    echo "请先安装 Claude Code CLI"
    echo "下载地址: https://docs.anthropic.com/zh-CN/docs/claude-code/CLI"
    echo ""
    read -p "按回车键退出..." REPLY
    exit 1
fi
echo "[3/3] Claude CLI: $(claude --version 2>&1 | head -1)"

echo ""
echo "========================================"
echo "  启动中...（关闭界面后按 Ctrl+C 退出）"
echo "========================================"
echo ""

python3 main.py
