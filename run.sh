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

# ===== 检测终端 =====

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

# ===== 寻找 Python =====

find_python() {
    for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
        if command -v "$candidate" &> /dev/null; then
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

# ===== 检查 PyQt6 =====

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

# ===== 自动更新 claude-agent-sdk =====

SDK_SOURCE_DIR="$DIR/claude-agent-sdk-source"
SDK_TARGET_DIR="$DIR/claude_agent_sdk"

# 读取当前已安装的 SDK 版本
CURRENT_VERSION=""
if [ -f "$SDK_TARGET_DIR/_version.py" ]; then
    CURRENT_VERSION=$("$PYTHON_CMD" -c "
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location('_version', os.path.join('$SDK_TARGET_DIR', '_version.py'))
mod = importlib.util.module_from_spec(spec)
sys.modules['_version'] = mod
spec.loader.exec_module(mod)
print(mod.__version__)
" 2>/dev/null)
fi

# 从 zip 压缩包中提取 SDK 的公共函数
extract_sdk_from_zip() {
    local zip_file="$1" target_ver="$2"
    local temp_dir=$(mktemp -d)
    unzip -q "$zip_file" -d "$temp_dir"

    local extract_root="$temp_dir"
    # 尝试精确匹配
    if [ -d "$temp_dir/claude-agent-sdk-python-$target_ver" ]; then
        extract_root="$temp_dir/claude-agent-sdk-python-$target_ver"
    else
        # fallback: 找第一个匹配的目录
        for d in "$temp_dir"/claude-agent-sdk-python-*; do
            if [ -d "$d" ]; then
                extract_root="$d"
                break
            fi
        done
    fi

    if [ -d "$extract_root/src/claude_agent_sdk" ]; then
        cp -r "$extract_root/src/claude_agent_sdk" "$SDK_TARGET_DIR"
    elif [ -d "$extract_root/claude_agent_sdk" ]; then
        cp -r "$extract_root/claude_agent_sdk" "$SDK_TARGET_DIR"
    else
        echo "[SDK] 警告: 未在 zip 中找到 claude_agent_sdk 目录"
        rm -rf "$temp_dir"
        return 1
    fi
    rm -rf "$temp_dir"
    return 0
}

# 扫描 source 目录中的 zip，找到最新版本
if [ -d "$SDK_SOURCE_DIR" ]; then
    LATEST_ZIP=""
    LATEST_VER=""

    for zip_file in "$SDK_SOURCE_DIR"/claude-agent-sdk-python-*.zip; do
        [ -f "$zip_file" ] || continue
        base=$(basename "$zip_file")
        ver=$(echo "$base" | sed 's/claude-agent-sdk-python-//; s/\.zip//')

        if [ -z "$LATEST_VER" ]; then
            LATEST_VER="$ver"
            LATEST_ZIP="$zip_file"
        else
            # 版本号比较：逐段比较
            is_newer_ver() {
                local a="$1" b="$2"
                [ "$a" = "$b" ] && return 1
                local IFS='.'
                local -a va vb
                read -ra va <<< "$a"
                read -ra vb <<< "$b"
                for i in 0 1 2; do
                    local ai=${va[$i]:-0}
                    local bi=${vb[$i]:-0}
                    if [ "$bi" -gt "$ai" ] 2>/dev/null; then return 0; fi
                    if [ "$bi" -lt "$ai" ] 2>/dev/null; then return 1; fi
                done
                return 1
            }
            if is_newer_ver "$LATEST_VER" "$ver"; then
                LATEST_VER="$ver"
                LATEST_ZIP="$zip_file"
            fi
        fi
    done

    if [ -n "$LATEST_VER" ]; then
        if [ -z "$CURRENT_VERSION" ]; then
            echo "[SDK] 未安装 → 自动安装 v${LATEST_VER}"
            extract_sdk_from_zip "$LATEST_ZIP" "$LATEST_VER"
        elif [ "$LATEST_VER" = "$CURRENT_VERSION" ]; then
            echo "[3/5] claude-agent-sdk: v${CURRENT_VERSION} (已是最新)"
        else
            echo "[SDK] 发现新版本: v${CURRENT_VERSION} → v${LATEST_VER}，自动更新..."
            rm -rf "$SDK_TARGET_DIR"
            extract_sdk_from_zip "$LATEST_ZIP" "$LATEST_VER"
            if [ $? -eq 0 ]; then
                echo "[SDK] 更新完成: v${LATEST_VER}"
            else
                echo "[SDK] 更新失败，回退到旧版本"
            fi
        fi
    fi
fi

# 检查 SDK 导入
if ! "$PYTHON_CMD" -c "import claude_agent_sdk" 2>/dev/null; then
    echo "[SDK] 正在安装依赖 (anyio, mcp, sniffio)..."
    "$PYTHON_CMD" -m pip install anyio mcp sniffio
    if [ $? -ne 0 ]; then
        echo "[错误] SDK 依赖安装失败"
        echo ""
        read -p "按回车键退出..." REPLY
        exit 1
    fi
    echo "SDK 依赖安装完成"
fi

# 读取最终 SDK 版本
FINAL_SDK_VERSION=$("$PYTHON_CMD" -c "
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location('_version', os.path.join('$SDK_TARGET_DIR', '_version.py'))
mod = importlib.util.module_from_spec(spec)
sys.modules['_version'] = mod
spec.loader.exec_module(mod)
print(mod.__version__)
" 2>/dev/null)
if [ -n "$FINAL_SDK_VERSION" ]; then
    echo "[3/5] claude-agent-sdk: v${FINAL_SDK_VERSION}"
else
    echo "[3/5] claude-agent-sdk: 已安装"
fi

# ===== 检查 claude CLI =====

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
