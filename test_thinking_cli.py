#!/usr/bin/env python3
"""独立测试脚本：直接调用 Claude CLI 检查 thinking 输出格式。"""
import subprocess
import json
import sys

prompt = "请简要分析一下 Python 中装饰器的工作原理，用中文回答。"

cmd = [
    "claude", "-p", prompt,
    "--output-format", "stream-json",
    "--include-partial-messages",
    "--verbose",
    "--thinking", "adaptive",
    "--thinking-display", "summarized",
]

print(f"执行命令: {' '.join(cmd)}")
print("=" * 60)

try:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    for line in proc.stdout:
        line = line.strip()
        if not line or not line.startswith("{"):
            continue

        try:
            data = json.loads(line)
            msg_type = data.get("type", "")

            if msg_type == "assistant":
                content = data.get("message", {}).get("content", [])
                print(f"\n[AssistantMessage] {len(content)} content blocks:")
                for i, block in enumerate(content):
                    btype = block.get("type", "")
                    print(f"  Block {i}: type={btype}")
                    if btype == "thinking":
                        thinking = block.get("thinking", "")
                        sig = block.get("signature", "")
                        print(f"    thinking length: {len(thinking)}")
                        print(f"    thinking preview: {thinking[:300]}")
                        print(f"    signature: {sig[:50]}...")
                    elif btype == "text":
                        text = block.get("text", "")
                        print(f"    text preview: {text[:200]}")

            elif msg_type == "result":
                print(f"\n[ResultMessage] is_error={data.get('is_error', '')}")
                break

        except json.JSONDecodeError:
            pass

    proc.wait(timeout=120)
    print(f"\n进程退出码: {proc.returncode}")

except Exception as e:
    print(f"错误: {e}")
