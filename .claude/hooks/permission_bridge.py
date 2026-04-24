#!/usr/bin/env python3
"""
CC-view 权限桥接脚本：将 Claude Code 的 PermissionRequest 转发给运行中的 CC-view GUI。
"""
import json
import os
import sys
import urllib.request
import urllib.error


def _log(line: str):
    """始终写入固定调试路径。"""
    try:
        log_path = "/tmp/permission_bridge_debug.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line.rstrip() + "\n")
    except Exception:
        pass

    # 同时尝试写入项目目录
    try:
        log_path = os.path.join(_project_dir(), ".claude", "permission_bridge.log")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
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
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def _find_hook_info():
    """在多个可能的位置搜索 cc_view_hook.json。"""
    candidates = []

    # 1. 当前项目目录（Claude Code 运行的目录）
    candidates.append(os.path.join(_project_dir(), ".claude", "cc_view_hook.json"))

    # 2. 用户 home 目录下的 .claude（全局配置）
    home = os.path.expanduser("~")
    candidates.append(os.path.join(home, ".claude", "cc_view_hook.json"))

    # 3. CC-view 自身目录（脚本所在的 CC-view 项目）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cc_view_dir = script_dir
    # 如果脚本在 .claude/hooks/ 下，往上两级到 CC-view 目录
    if os.path.basename(cc_view_dir) == "hooks":
        cc_view_dir = os.path.dirname(os.path.dirname(cc_view_dir))
    candidates.append(os.path.join(cc_view_dir, ".claude", "cc_view_hook.json"))

    # 4. 环境变量指定的目录
    env_dir = os.environ.get("CCVIEW_PROJECT_DIR")
    if env_dir:
        candidates.append(os.path.join(env_dir, ".claude", "cc_view_hook.json"))

    for path in candidates:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "port" in data and "token" in data:
                    _log(f"[hook] found config at {path}")
                    return data
        except Exception as e:
            _log(f"[hook] failed to read {path}: {e}")

    return None


def _post_permission(event, hook_info):
    url = f"http://127.0.0.1:{hook_info['port']}/permission"
    _log(f"[hook] posting to {url}")
    data = json.dumps(event, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    req.add_header("X-CCVIEW-TOKEN", hook_info["token"])
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body.strip() else {}
    except urllib.error.HTTPError as e:
        _log(f"[hook] HTTP error: {e.code} {e.reason}")
        raise
    except urllib.error.URLError as e:
        _log(f"[hook] URL error: {e.reason}")
        raise
    except Exception as e:
        _log(f"[hook] unexpected error: {type(e).__name__}: {e}")
        raise


def main():
    event = _read_stdin_json()
    _log(f"[hook] event={event.get('hook_event_name')} tool={event.get('tool_name')}")

    # 搜索 CC-view hook 配置
    hook_info = _find_hook_info()
    if not hook_info:
        _log("[hook] no hook info found in any location; passthrough")
        return 0

    _log(f"[hook] loaded hook info: port={hook_info.get('port')}, token_len={len(hook_info.get('token', ''))}")

    try:
        decision = _post_permission(event, hook_info)
        _log(f"[hook] post success: decision={decision}")
    except urllib.error.URLError as e:
        _log(f"[hook] connection failed: {e}; passthrough")
        return 0
    except Exception as e:
        _log(f"[hook] post failed: {e}; passthrough")
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
