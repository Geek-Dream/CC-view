#!/usr/bin/env python3
"""直接测试 Claude Code 的 PermissionRequest hook。"""
import json
import subprocess
import os
import tempfile
import time
import threading

# 创建临时 settings
override_settings = {
    "permissions": {"defaultMode": "default"},
    "skipAutoPermissionPrompt": False,
    "skipDangerousModePermissionPrompt": False,
}
settings_file = tempfile.NamedTemporaryFile(
    mode="w", suffix=".json", delete=False, prefix="ccview_test_",
    encoding="utf-8"
)
json.dump(override_settings, settings_file)
settings_file.close()
print(f"Settings file: {settings_file.name}")
print(f"Settings content: {json.dumps(override_settings, indent=2)}")

# 清空 hook 日志
log_path = os.path.expanduser("~/.claude/permission_bridge.log")
open(log_path, "w").close()

cmd = [
    "claude",
    "-p", "在当前目录创建一个 test_hook.txt 文件，内容是 hook_test",
    "--model", "MiniMax-M2.7-highspeed",
    "--output-format", "stream-json",
    "--include-partial-messages",
    "--verbose",
    "--permission-mode", "default",
    "--settings", settings_file.name,
]

print(f"\n命令: {' '.join(cmd)}\n")
print(f"工作目录: {os.getcwd()}")
print(f"\n等待 30 秒让 Claude 执行...\n")

proc = subprocess.Popen(
    cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
)

# 监控输出
tool_use_found = False
stop_reason = None
start = time.time()
for line in proc.stdout:
    line = line.strip()
    if not line:
        continue
    try:
        obj = json.loads(line)
    except:
        continue

    msg_type = obj.get("type", "")
    if msg_type == "stream_event":
        event = obj.get("event", {})
        event_type = event.get("type", "")
        if event_type == "content_block_start":
            block = event.get("content_block", {})
            if block.get("type") == "tool_use":
                tool_use_found = True
                print(f"[TOOL CALL] {block.get('name')}")
        elif event_type == "message_delta":
            stop_reason = event.get("stop_reason")
            print(f"[STOP] {stop_reason}")
    elif msg_type == "system":
        init = obj.get("subtype", "")
        if init == "init":
            print(f"[SESSION] model={obj.get('model')}")

    if time.time() - start > 25:
        print("[TIMEOUT] 25s reached, stopping")
        proc.kill()
        break

if tool_use_found:
    print("\n=== Tool call detected ===")
    print("检查 hook 日志是否被触发:")

# 等待进程结束或超时
try:
    proc.wait(timeout=30)
except:
    proc.kill()

# 检查 hook 日志
print("\n=== Hook 日志 ===")
try:
    with open(log_path, "r") as f:
        content = f.read()
        if content:
            print(content)
        else:
            print("(空 - hook 脚本从未被调用)")
except:
    print("无法读取 hook 日志")

# 清理
os.unlink(settings_file.name)
print("\n测试完成")
