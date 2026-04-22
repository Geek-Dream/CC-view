#!/usr/bin/env python3
import json
import os
import sys
import urllib.request


def _log(line: str):
    try:
        log_path = os.path.join(_project_dir(), ".claude", "permission_bridge.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line.rstrip() + "\n")
    except Exception:
        pass


def _read_stdin_json():
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    return json.loads(raw)


def _project_dir():
    # Claude Code provides this env var for hooks
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def _load_hook_info():
    path = os.path.join(_project_dir(), ".claude", "cc_view_hook.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _post_permission(event, hook_info):
    url = f"http://127.0.0.1:{hook_info['port']}/permission"
    data = json.dumps(event, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    req.add_header("X-CCVIEW-TOKEN", hook_info["token"])
    with urllib.request.urlopen(req, timeout=600) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body.strip() else {}


def main():
    event = _read_stdin_json()
    _log(f"[hook] event={event.get('hook_event_name')} tool={event.get('tool_name')}")

    # 默认：不拦截（让 Claude Code 自己弹 TUI）
    # 但当 cc-view GUI 正在运行且写出了 hook info 文件时，我们接管权限对话框。
    try:
        hook_info = _load_hook_info()
    except Exception:
        _log("[hook] no hook info; passthrough")
        return 0

    try:
        decision = _post_permission(event, hook_info)
    except Exception:
        _log("[hook] post failed; passthrough")
        return 0

    behavior = decision.get("behavior")
    if behavior not in ("allow", "deny"):
        _log(f"[hook] invalid decision={decision}; passthrough")
        return 0

    _log(f"[hook] decision={decision}")
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": decision,
        }
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

