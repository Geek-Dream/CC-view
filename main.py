#!/usr/bin/env python3
"""Claude Code 桌面助手 — PyQt6 版本，跨平台兼容 (Windows/Mac/Linux)。"""
import sys
import os
import json
import uuid
import subprocess
from datetime import datetime
import threading
import secrets
from http.server import BaseHTTPRequestHandler, HTTPServer

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QComboBox, QInputDialog,
    QListWidget, QListWidgetItem, QScrollArea, QFrame,
    QDialog, QFileDialog, QMessageBox, QSizePolicy, QMenu,
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QObject, pyqtSlot, QPropertyAnimation, QEasingCurve, QRect, QPoint
from PyQt6.QtGui import QFont, QColor, QIcon

from claude_client import ClaudeClient

# ==================== 数据目录 ====================

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "conversations")
os.makedirs(DATA_DIR, exist_ok=True)

# ==================== 深色主题令牌 ====================

THEME = {
    "bg_primary": "#0F0F14",    # 深空黑 主背景
    "bg_secondary": "#1A1A2E",  # 侧边栏背景
    "bg_card": "#25253D",       # 卡片背景
    "bg_input": "#1E1E35",      # 输入框背景
    "border": "#2D2D4A",        # 边框色
    "border_focus": "#6366F1",  # 聚焦边框
    "primary": "#6366F1",       # 紫蓝主题色
    "primary_hover": "#818CF8", # 悬停色
    "red": "#EF4444",           # 停止/错误
    "red_hover": "#DC2626",
    "green": "#22C55E",         # 成功
    "green_hover": "#16A34A",
    "orange": "#F97316",
    "purple": "#A855F7",
    "teal": "#0D9488",
    "text_primary": "#E2E8F0",  # 主文字
    "text_secondary": "#94A3B8",# 次要文字
    "text_tertiary": "#64748B", # 弱提示
    "user_bubble": "#1E3A2F",   # 用户气泡
    "user_text": "#6EE7B7",
    "ai_bubble": "#25253D",     # AI 气泡
    "ai_text": "#E2E8F0",
    "system_bubble": "#1E293B", # 系统气泡
    "system_text": "#93C5FD",
    "thinking_bg": "#1A1A2E",   # 思考块背景
    "thinking_border": "#2D2D4A",
}

# ==================== 内置数据 ====================

PROMPT_TEMPLATES = {
    "代码审查": "请审查以下代码，指出潜在问题和改进建议：",
    "写单元测试": "请为以下代码编写完整的单元测试：",
    "解释代码": "请详细解释以下代码的工作原理：",
    "性能优化": "请分析以下代码的性能瓶颈并提供优化方案：",
    "生成文档": "请为以下代码生成清晰的中文注释和文档：",
}

AGENT_LIST = [
    ("general-purpose", "通用智能体 — 处理复杂多步任务"),
    ("Explore", "快速探索 — 搜索和查找代码"),
    ("Plan", "软件架构师 — 设计实现方案"),
]

SKILLS_LIST = [
    ("commit", "创建 git 提交"),
    ("review-pr", "审查拉取请求"),
    ("simplify", "审查代码质量并优化"),
    ("security-review", "安全审查"),
]


# ==================== 对话持久化 ====================

def save_conversation(conv_id, title, messages, session_id=None):
    filepath = os.path.join(DATA_DIR, f"{conv_id}.json")
    data = {
        "id": conv_id,
        "title": title,
        "created_at": datetime.now().isoformat(),
        "messages": messages,
    }
    if session_id is not None:
        data["session_id"] = session_id
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_conversation(conv_id):
    filepath = os.path.join(DATA_DIR, f"{conv_id}.json")
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def list_conversations():
    convs = []
    if not os.path.exists(DATA_DIR):
        return convs
    for fname in sorted(os.listdir(DATA_DIR), reverse=True):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(DATA_DIR, fname), "r", encoding="utf-8") as f:
                    data = json.load(f)
                convs.append(data)
            except Exception:
                pass
    return convs


# ==================== 后台工作线程 ====================

class GitWorker(QObject):
    """后台执行 git 命令，不阻塞 UI。"""
    files_ready = pyqtSignal(list)
    status_ready = pyqtSignal(dict)

    @pyqtSlot()
    def fetch_files(self):
        try:
            r = subprocess.run(["git", "ls-files"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                files = [f for f in r.stdout.strip().split("\n") if f]
                self.files_ready.emit(files)
                return
        except Exception:
            pass
        self.files_ready.emit([])

    @pyqtSlot()
    def fetch_status(self):
        try:
            r = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                result = {"modified": [], "added": [], "deleted": []}
                for line in r.stdout.strip().split("\n"):
                    if not line:
                        continue
                    status = line[:2].strip()
                    path = line[3:]
                    if status in ("M", "MM"):
                        result["modified"].append(path)
                    elif status in ("A", "??"):
                        result["added"].append(path)
                    else:
                        result["deleted"].append(path)
                self.status_ready.emit(result)
                return
        except Exception:
            pass
        self.status_ready.emit({"modified": [], "added": [], "deleted": []})


class ClaudeWorker(QObject):
    """后台执行 claude 命令，流式输出。"""
    chunk_ready = pyqtSignal(str)           # 流式文本片段
    result_ready = pyqtSignal(str)          # 最终结果
    session_ready = pyqtSignal(str)         # session_id（新对话首次创建）
    thinking_started = pyqtSignal()         # 开始思考
    thinking_ready = pyqtSignal(str, int)   # 单段思考完成（文本, 用时ms）
    status_update = pyqtSignal(str)         # 过程状态（用于前端反馈）
    error_occurred = pyqtSignal(str)
    stopped = pyqtSignal()                  # 用户主动终止

    def __init__(self, prompt, model, session_id=None, permission_mode="default"):
        super().__init__()
        self.prompt = prompt
        self.model = model
        self.session_id = session_id  # 已有 session 则传入 --resume 续接
        self.permission_mode = permission_mode or "default"
        self._stop_requested = False
        self._proc = None

    def stop(self):
        """用户主动终止 Claude 回复。"""
        self._stop_requested = True
        if self._proc and self._proc.poll() is None:
            self._proc.kill()

    @pyqtSlot()
    def run(self):
        try:
            cmd = [
                "claude", "-p", self.prompt,
                "--model", self.model,
                "--output-format", "stream-json",
                "--include-partial-messages",
                "--verbose",
                "--permission-mode", self.permission_mode,
            ]
            # 如果有 session_id，续接该会话
            if self.session_id:
                cmd.extend(["--resume", self.session_id])
                print(f"[ClaudeWorker] 续接 session: {self.session_id}")
            else:
                print(f"[ClaudeWorker] 新对话")

            print(f"\n{'='*60}")
            print(f"[USER] {self.prompt}")
            print(f"{'='*60}")

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # 合并输出，避免 stderr 阻塞
            )
            self._proc = proc

            # 用 TextIOWrapper 处理行缓冲
            import io
            import time
            stdout = io.TextIOWrapper(proc.stdout, encoding="utf-8", errors="replace", line_buffering=True)

            full_text = ""          # 累积正式回复文本
            thinking_text = ""      # 累积思考内容
            thinking_start_time = 0 # 思考开始时间戳
            thinking_emitted = False # 防止同一消息重复触发思考信号

            while True:
                if self._stop_requested:
                    print(f"[ClaudeWorker] 收到停止请求")
                    proc.kill()
                    self.stopped.emit()
                    return
                if proc.poll() is not None:
                    # 进程已退出
                    break
                line = stdout.readline()
                if not line:
                    # EOF
                    break
                decoded = line.strip()
                if not decoded:
                    continue

                try:
                    obj = json.loads(decoded)
                except json.JSONDecodeError:
                    continue

                msg_type = obj.get("type", "")

                # 系统初始化信息
                if msg_type == "system":
                    sub = obj.get("subtype", "")
                    if sub == "init":
                        session_id = obj.get("session_id", "")
                        model_info = obj.get("model", "")
                        version = obj.get("claude_code_version", "")
                        print(f"[SYSTEM] session={session_id} model={model_info} version={version}")
                        # 新对话：回传 session_id 给主线程保存
                        if session_id:
                            self.session_ready.emit(session_id)
                    elif sub == "status":
                        status_text = obj.get("status", "")
                        print(f"[SYSTEM] status={status_text}")
                        if status_text:
                            self.status_update.emit(f"状态: {status_text}")
                    elif sub == "api_retry":
                        attempt = obj.get("attempt", 0)
                        max_retries = obj.get("max_retries", 0)
                        error = obj.get("error", "")
                        delay_ms = obj.get("retry_delay_ms", 0)
                        print(f"[SYSTEM] api_retry attempt={attempt}/{max_retries} error={error} delay={delay_ms:.0f}ms")
                        self.status_update.emit(f"接口重试: 第{attempt}/{max_retries}次")

                # 流式事件
                elif msg_type == "stream_event":
                    event = obj.get("event", {})
                    event_type = event.get("type", "")

                    if event_type == "message_start":
                        msg_id = event.get("message", {}).get("id", "")
                        print(f"[EVENT] message_start id={msg_id[:16]}...")
                        thinking_emitted = False
                        self.status_update.emit("开始生成回复")

                    elif event_type == "content_block_start":
                        block = event.get("content_block", {})
                        block_type = block.get("type", "")
                        print(f"[EVENT] content_block_start index={event.get('index', '')} type={block_type}")

                        if block_type == "thinking":
                            thinking_start_time = time.time()
                            thinking_text = ""
                            self.thinking_started.emit()
                            self.status_update.emit("正在深度思考")
                        elif block_type == "tool_use":
                            self.status_update.emit("正在调用工具")
                        elif block_type == "text":
                            self.status_update.emit("正在组织输出")

                    elif event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        delta_type = delta.get("type", "")
                        if delta_type == "text_delta":
                            text = delta.get("text", "")
                            full_text += text
                            self.chunk_ready.emit(full_text)
                        elif delta_type == "thinking_delta":
                            thinking_text += delta.get("thinking", "")

                    elif event_type == "content_block_stop":
                        # 思考块结束：计算用时，回传思考内容
                        # 加防重标志，避免 text block 的 stop 误触发
                        if thinking_text and thinking_start_time > 0 and not thinking_emitted:
                            duration_ms = int((time.time() - thinking_start_time) * 1000)
                            preview = thinking_text[:100].replace("\n", " ")
                            print(f"[THINKING] {preview}... ({duration_ms}ms)")
                            self.thinking_ready.emit(thinking_text, duration_ms)
                            thinking_emitted = True
                            thinking_text = ""
                            thinking_start_time = 0
                            self.status_update.emit("思考完成，继续处理")

                    elif event_type == "message_delta":
                        stop = event.get("delta", {}).get("stop_reason", "")
                        usage = event.get("delta", {}).get("usage", {})
                        output_tokens = usage.get("output_tokens", 0)
                        print(f"[EVENT] message_delta stop={stop} output_tokens={output_tokens}")

                    elif event_type == "message_stop":
                        print(f"[EVENT] message_stop")

                # 最终结果
                elif msg_type == "result":
                    result_text = obj.get("result", "")
                    is_error = obj.get("is_error", False)
                    duration = obj.get("duration_ms", 0)
                    cost = obj.get("total_cost_usd", 0)
                    usage = obj.get("usage", {})
                    input_tokens = usage.get("input_tokens", 0)
                    output_tokens = usage.get("output_tokens", 0)
                    stop_reason = obj.get("stop_reason", "")
                    terminal_reason = obj.get("terminal_reason", "")

                    print(f"\n[AI] {result_text}")
                    print(f"{'='*60}")
                    print(f"[RESULT] success={not is_error} duration={duration}ms cost=${cost:.6f}")
                    print(f"[RESULT] tokens=输入{input_tokens}/输出{output_tokens} stop={stop_reason}({terminal_reason})")
                    print(f"{'='*60}\n")

                    if result_text and not is_error:
                        self.result_ready.emit(result_text)
                    else:
                        if is_error:
                            self.error_occurred.emit(result_text or "未知错误")
                        else:
                            self.result_ready.emit(full_text)
                    return

            # 如果没有收到 result 消息但有累积文本，检查退出码
            if self._stop_requested:
                # 用户主动终止，不触发 result/error 信号，直接返回
                self.stopped.emit()
                return
            if full_text:
                proc.wait()
                if proc.returncode == 0:
                    self.result_ready.emit(full_text)
                else:
                    self.error_occurred.emit(f"进程异常退出 (code: {proc.returncode})")

        except Exception as e:
            print(f"[ClaudeWorker] 错误: {e}")
            self.error_occurred.emit(str(e))


class TitleWorker(QThread):
    """后台生成对话标题，单次独立请求，不加入 session。"""
    title_ready = pyqtSignal(str)

    def __init__(self, user_message, ai_reply):
        super().__init__()
        self.user_message = user_message
        self.ai_reply = ai_reply
        self._timeout = 30

    def run(self):
        try:
            prompt = (
                f"请用一句话总结以下对话内容，作为对话标题，不超过15个字。\n"
                f"只输出标题文本，不要解释，不要加任何标点符号。\n\n"
                f"User: {self.user_message[:300]}\n"
                f"Assistant: {self.ai_reply[:500]}"
            )
            cmd = [
                "claude", "-p", prompt,
                "--model", "haiku",
                "--no-session-persistence",
            ]
            print(f"[TitleWorker] 启动")
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            title = proc.stdout.strip()
            # 清理：去掉 markdown 符号、引号、前后缀
            title = title.lstrip("#*`- ").strip().strip('"').strip("'").strip()
            # 只取第一行
            title = title.split("\n")[0].strip()
            if title and len(title) > 15:
                title = title[:15] + "…"
            if title:
                print(f"[TitleWorker] 生成标题: {title}")
                self.title_ready.emit(title)
            else:
                print(f"[TitleWorker] 未生成有效标题, returncode={proc.returncode}")
        except subprocess.TimeoutExpired:
            print(f"[TitleWorker] 超时（{self._timeout}s）")
        except Exception as e:
            print(f"[TitleWorker] 异常: {e}")


# ==================== 消息气泡 ====================

class MessageRow(QWidget):
    """消息气泡，QLabel 支持文字选择复制。"""

    def __init__(self, role, text, parent=None):
        super().__init__(parent)
        self.role = role
        self._thinking_dots = 0
        self._is_thinking = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(0)

        bubble = QFrame()
        bubble.setObjectName("bubble")
        bubble.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)

        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(0, 0, 0, 0)
        bubble_layout.setSpacing(0)

        prefix = {"user": "你", "assistant": "AI", "system": "系统"}.get(role, "?")
        prefix_label = QLabel(prefix)
        prefix_label.setStyleSheet("font-weight: bold; font-size: 11px; padding: 4px 10px 0 10px;")
        bubble_layout.addWidget(prefix_label)

        content = QLabel(text)
        content.setWordWrap(True)
        content.setStyleSheet("font-size: 13px; padding: 4px 10px 8px 10px;")
        content.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        bubble_layout.addWidget(content)

        # 样式 — 深色主题
        if role == "user":
            bubble.setStyleSheet(f"""
                #bubble {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 {THEME['user_bubble']}, stop:1 #162923);
                    border-radius: 12px;
                    border: 1px solid #2D4A3A;
                }}
                #bubble QLabel {{ color: {THEME['user_text']}; background: transparent; }}
            """)
            layout.addStretch()
            layout.addWidget(bubble)
        elif role == "system":
            bubble.setStyleSheet(f"""
                #bubble {{
                    background-color: {THEME['system_bubble']}; border-radius: 12px;
                    border: 1px solid #2D3A4A;
                }}
                #bubble QLabel {{ color: {THEME['system_text']}; background: transparent; }}
            """)
            layout.addWidget(bubble)
            layout.addStretch()
        else:
            bubble.setStyleSheet(f"""
                #bubble {{
                    background-color: {THEME['ai_bubble']}; border-radius: 12px;
                    border: 1px solid {THEME['border']};
                }}
                #bubble QLabel {{ color: {THEME['ai_text']}; background: transparent; }}
            """)
            layout.addWidget(bubble)
            layout.addStretch()

        self._content_label = content

        # 如果是 AI 消息，启动思考动画
        if role == "assistant" and text == "思考中...":
            self._start_thinking_animation()

    def _start_thinking_animation(self):
        """启动思考动画。"""
        self._is_thinking = True
        self._thinking_dots = 0
        self._thinking_timer = QTimer()
        self._thinking_timer.timeout.connect(self._update_thinking)
        self._thinking_timer.start(400)

    def _update_thinking(self):
        """更新思考动画。"""
        if not self._is_thinking:
            return
        self._thinking_dots = (self._thinking_dots + 1) % 4
        dots = "." * self._thinking_dots
        self._content_label.setText(f"🤔 思考中{dots}")

    def _start_processing_animation(self, base_text):
        """启动处理中动画（转圈）。"""
        self._processing_base_text = base_text
        self._processing_idx = 0
        self._processing_frames = ["◐", "◓", "◑", "◒"]
        if hasattr(self, "_processing_timer") and self._processing_timer:
            self._processing_timer.stop()
        self._processing_timer = QTimer()
        self._processing_timer.timeout.connect(self._update_processing)
        self._processing_timer.start(160)

    def _stop_processing_animation(self):
        if hasattr(self, "_processing_timer") and self._processing_timer:
            self._processing_timer.stop()
            self._processing_timer = None

    def _update_processing(self):
        frame = self._processing_frames[self._processing_idx % len(self._processing_frames)]
        self._processing_idx += 1
        # 展示 “◐ 处理中：xxx”
        self._content_label.setText(f"{frame} {self._processing_base_text}")

    def _type_next_char(self):
        """打字机动画：每次显示一个字符。"""
        if not hasattr(self, '_target_text'):
            return
        self._displayed_chars += 1
        if self._displayed_chars >= len(self._target_text):
            # 动画完成
            self._content_label.setText(self._target_text)
            if hasattr(self, '_type_timer'):
                self._type_timer.stop()
                del self._type_timer
            return
        self._content_label.setText(self._target_text[:self._displayed_chars])

    def update_text(self, text):
        """更新消息文字（用于流式输出）。"""
        if not hasattr(self, '_content_label'):
            return
        # 处理中状态：持续动画提示（正文开始前的过程态）
        if self.role == "assistant" and isinstance(text, str) and text.startswith("处理中："):
            base = text
            # 避免重复启动 timer
            current = getattr(self, "_processing_base_text", None)
            if current != base:
                self._start_processing_animation(base)
            return
        else:
            self._stop_processing_animation()
        # 停止思考动画
        if self._is_thinking:
            self._is_thinking = False
            if hasattr(self, '_thinking_timer'):
                self._thinking_timer.stop()
            # 开始打字机动画，从第一个字开始
            self._target_text = text
            self._displayed_chars = 0
            if hasattr(self, '_type_timer'):
                self._type_timer.stop()
            self._type_timer = QTimer()
            self._type_timer.timeout.connect(self._type_next_char)
            self._type_timer.start(20)  # 每字 20ms（约 50 字/秒）
            return
        # 非思考状态，直接显示或继续动画
        current = self._content_label.text()
        if text == current:
            return
        if len(text) <= len(current):
            self._content_label.setText(text)
            return
        # 新的更长文本，继续动画
        self._target_text = text
        if not hasattr(self, '_type_timer') or not self._type_timer.isActive():
            self._displayed_chars = len(current)
            self._type_timer = QTimer()
            self._type_timer.timeout.connect(self._type_next_char)
            self._type_timer.start(20)

    def get_text(self):
        """获取当前显示文本。"""
        if not hasattr(self, '_content_label'):
            return ""
        return self._content_label.text()


class ThinkingBlock(QFrame):
    """可折叠的思考内容块。"""

    def __init__(self, text, duration_ms, parent=None):
        super().__init__(parent)
        self.setObjectName("thinkingBlock")
        self._expanded = False
        self._entries = []
        self._total_duration_ms = 0
        self._in_progress = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题栏（可点击）
        header = QFrame()
        header.setObjectName("thinkingHeader")
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(8, 6, 8, 6)
        h_layout.setSpacing(6)

        icon_label = QLabel("[思考]")
        icon_label.setStyleSheet(f"font-weight: bold; font-size: 12px; color: {THEME['text_tertiary']};")
        h_layout.addWidget(icon_label)

        self._title_label = QLabel("深度思考中")
        self._title_label.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {THEME['text_secondary']};")
        h_layout.addWidget(self._title_label)

        self._duration_label = QLabel("（用时 0毫秒）")
        self._duration_label.setStyleSheet(f"font-size: 12px; color: {THEME['text_tertiary']};")
        h_layout.addWidget(self._duration_label)

        h_layout.addStretch()

        self._arrow_label = QLabel("▶")
        self._arrow_label.setStyleSheet(f"font-size: 10px; color: {THEME['text_tertiary']};")
        h_layout.addWidget(self._arrow_label)

        layout.addWidget(header)

        # 内容区（默认折叠）
        self._content_frame = QFrame()
        self._content_frame.setObjectName("thinkingContent")
        c_layout = QVBoxLayout(self._content_frame)
        c_layout.setContentsMargins(10, 0, 10, 8)
        c_layout.setSpacing(0)

        self._content_label = QLabel("")
        self._content_label.setWordWrap(True)
        self._content_label.setStyleSheet(f"font-size: 12px; color: {THEME['text_secondary']}; line-height: 1.6;")
        self._content_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        c_layout.addWidget(self._content_label)

        self._content_frame.setVisible(False)
        layout.addWidget(self._content_frame)

        # 样式 — 深色主题
        self.setStyleSheet(f"""
            #thinkingBlock {{
                background-color: {THEME['thinking_bg']};
                border: 1px solid {THEME['thinking_border']};
                border-radius: 10px; margin: 2px 0;
            }}
            #thinkingHeader {{ background-color: transparent; }}
            #thinkingContent {{ background-color: transparent; }}
        """)

        # 点击切换展开/折叠
        def toggle():
            self._expanded = not self._expanded
            self._content_frame.setVisible(self._expanded)
            self._arrow_label.setText("▼" if self._expanded else "▶")

        header.mousePressEvent = lambda e: toggle()
        self.append_entry(text, duration_ms)

    def append_entry(self, text, duration_ms):
        """追加一段思考内容。"""
        clean_text = (text or "").strip()
        if not clean_text:
            return
        self._entries.append({"text": clean_text, "duration_ms": max(0, int(duration_ms or 0))})
        self._total_duration_ms += max(0, int(duration_ms or 0))
        self._refresh_content()

    def set_in_progress(self, in_progress):
        """更新思考状态。"""
        self._in_progress = bool(in_progress)
        self._refresh_header()

    def _refresh_content(self):
        parts = []
        for idx, entry in enumerate(self._entries, start=1):
            parts.append(f"[第{idx}段 | 用时 {self._format_duration(entry['duration_ms'])}]")
            parts.append(entry["text"])
            parts.append("")
        self._content_label.setText("\n".join(parts).strip())
        self._refresh_header()

    def _refresh_header(self):
        count = len(self._entries)
        if self._in_progress:
            self._title_label.setText(f"深度思考中（已记录{count}段）")
        else:
            self._title_label.setText(f"深度思考已完成（共{count}段）")
        self._duration_label.setText(f"（累计用时 {self._format_duration(self._total_duration_ms)}）")

    @staticmethod
    def _format_duration(ms):
        """格式化时间为 分/秒/毫秒。"""
        try:
            ms = int(ms or 0)
        except Exception:
            ms = 0
        if ms < 0:
            ms = 0
        minutes = ms // 60000
        seconds = (ms % 60000) // 1000
        millis = ms % 1000

        parts = []
        if minutes > 0:
            parts.append(f"{minutes}分")
        if seconds > 0 or minutes > 0:
            parts.append(f"{seconds}秒")
        # 低于 1 秒时显示毫秒；否则只在有毫秒余数时显示
        if minutes == 0 and seconds == 0:
            parts.append(f"{millis}毫秒")
        elif millis > 0:
            parts.append(f"{millis}毫秒")
        return "".join(parts) if parts else "0毫秒"


class ThinkingRow(QWidget):
    """思考行容器，包含一个 ThinkingBlock。"""

    def __init__(self, text, duration_ms, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(0)
        self._block = ThinkingBlock(text, duration_ms)
        layout.addWidget(self._block)
        layout.addStretch()

    def append_thinking(self, text, duration_ms):
        self._block.append_entry(text, duration_ms)

    def set_in_progress(self, in_progress):
        self._block.set_in_progress(in_progress)


class LandingPage(QFrame):
    """空状态引导页，无对话时显示 — 深色主题 + 浮动动画。"""

    send_clicked = pyqtSignal(str)  # 用户从着陆页发送消息

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("landingPage")
        self.setVisible(False)
        self.setStyleSheet(f"""
            #landingPage {{
                background-color: {THEME['bg_primary']};
            }}
        """)

        # 透明度效果
        self._opacity_effect = None
        self._fade_animation = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        # 顶部渐变文字
        hint_top = QLabel("你好，我是 Claude")
        hint_top.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_top.setStyleSheet(f"""
            font-size: 30px; color: {THEME['text_primary']};
            font-weight: bold; margin-bottom: 6px;
        """)
        layout.addWidget(hint_top)

        hint_sub = QLabel("我可以帮你写代码、回答问题、分析文件")
        hint_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_sub.setStyleSheet(f"font-size: 15px; color: {THEME['text_tertiary']};")
        layout.addWidget(hint_sub)

        layout.addSpacing(30)
        layout.addStretch()

        # 居中容器
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setSpacing(20)

        # 图标区域 — 紫蓝渐变圆形 + 浮动动画
        icon_label = QLabel("✦")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setMinimumSize(96, 96)
        icon_label.setMaximumSize(96, 96)
        icon_label.setStyleSheet(f"""
            QLabel {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {THEME['primary']}, stop:1 #8B5CF6);
                border-radius: 48px; font-size: 44px; color: white;
            }}
        """)
        self._icon_label = icon_label  # 保存引用用于动画
        center_layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # 文字提示
        hint_label = QLabel("请开始我们的对话吧")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_label.setStyleSheet(f"font-size: 16px; color: {THEME['text_tertiary']};")
        center_layout.addWidget(hint_label)

        # 输入区
        input_layout = QHBoxLayout()
        input_layout.setSpacing(10)

        self._input = QTextEdit()
        self._input.setPlaceholderText("输入消息...")
        self._input.setMinimumHeight(48)
        self._input.setMaximumHeight(100)
        self._input.setStyleSheet(f"""
            QTextEdit {{
                border: 1px solid {THEME['border']}; border-radius: 12px;
                padding: 10px 14px; font-size: 14px;
                background-color: {THEME['bg_input']}; color: {THEME['text_primary']};
            }}
            QTextEdit:focus {{ border-color: {THEME['border_focus']}; }}
            QTextEdit::placeholder {{ color: {THEME['text_tertiary']}; }}
        """)
        input_layout.addWidget(self._input)

        self._send_btn = QPushButton("发  送")
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {THEME['primary']}, stop:1 #8B5CF6);
                color: white; border: none; border-radius: 12px;
                padding: 10px 24px; font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {THEME['primary_hover']}, stop:1 #A78BFA);
            }}
            QPushButton:pressed {{ opacity: 0.85; }}
        """)
        self._send_btn.setMinimumHeight(48)
        input_layout.addWidget(self._send_btn)

        center_layout.addLayout(input_layout)

        layout.addWidget(center)
        layout.addStretch()

        # 信号
        self._send_btn.clicked.connect(self._on_send)
        self._input.keyPressEvent = self._on_key_press

    def _on_send(self):
        text = self._input.toPlainText().strip()
        if text:
            self._input.clear()
            self.send_clicked.emit(text)

    def _on_key_press(self, event):
        if event.key() == Qt.Key.Key_Return and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self._on_send()
            return
        QTextEdit.keyPressEvent(self._input, event)

    def get_input_text(self):
        return self._input.toPlainText().strip()

    def clear_input(self):
        self._input.clear()

    def fade_in(self, duration=500):
        """淡入动画。"""
        from PyQt6.QtWidgets import QGraphicsOpacityEffect

        self.setVisible(True)
        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(0.0)
        self.setGraphicsEffect(effect)
        self._opacity_effect = effect

        self._fade_animation = QPropertyAnimation(effect, b"opacity")
        self._fade_animation.setDuration(duration)
        self._fade_animation.setStartValue(0.0)
        self._fade_animation.setEndValue(1.0)
        self._fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_animation.start()
        self._anim_ref = self._fade_animation

    def fade_out(self, duration=300, callback=None):
        """淡出动画。"""
        from PyQt6.QtWidgets import QGraphicsOpacityEffect

        # 如果还没有 effect，创建一个
        if self._opacity_effect is None:
            effect = QGraphicsOpacityEffect(self)
            effect.setOpacity(1.0)
            self.setGraphicsEffect(effect)
            self._opacity_effect = effect

        self._fade_animation = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_animation.setDuration(duration)
        self._fade_animation.setStartValue(1.0)
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.setEasingCurve(QEasingCurve.Type.InCubic)

        def on_done():
            self.setVisible(False)
            if callback:
                callback()

        self._fade_animation.finished.connect(on_done)
        self._fade_animation.start()
        self._anim_ref = self._fade_animation


class PopupList(QDialog):
    """弹出选择列表对话框。"""

    def __init__(self, title, items, parent=None):
        super().__init__(parent)
        self.selected = None
        self.setWindowTitle(title)
        self.setMinimumWidth(380)
        self.setMinimumHeight(200)
        self.resize(380, 220)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {THEME['bg_secondary']};
            }}
        """)
        layout = QVBoxLayout(self)

        title_label = QLabel(title)
        title_label.setStyleSheet(f"font-weight: bold; font-size: 14px; padding: 8px; color: {THEME['text_primary']};")
        layout.addWidget(title_label)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                border: 1px solid {THEME['border']}; border-radius: 8px;
                background-color: {THEME['bg_card']}; color: {THEME['text_secondary']};
            }}
            QListWidget::item {{
                padding: 8px 12px; border-bottom: 1px solid {THEME['border']};
                color: {THEME['text_secondary']};
            }}
            QListWidget::item:hover {{ background-color: {THEME['bg_secondary']}; }}
            QListWidget::item:selected {{
                background-color: {THEME['primary']}; color: white;
                border-radius: 4px;
            }}
        """)
        for name, desc in items:
            item = QListWidgetItem(f"{name}  —  {desc}")
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget)
        self.list_widget.itemDoubleClicked.connect(self._on_select)

    def _on_select(self, item):
        self.selected = item.data(Qt.ItemDataRole.UserRole)
        self.accept()


# ==================== 面板 ====================

class LeftPanel(QFrame):
    """左侧面板：新建对话 + 历史对话列表。"""

    rename_requested = pyqtSignal(str)  # conv_id
    delete_requested = pyqtSignal(str)  # conv_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(240)
        self.setStyleSheet(f"""
            LeftPanel {{
                background-color: {THEME['bg_secondary']};
                border-right: 1px solid {THEME['border']};
            }}
        """)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(6)

        self.new_btn = QPushButton("✚ 新建对话")
        self.new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {THEME['primary']}, stop:1 #8B5CF6);
                color: white; border: none; border-radius: 8px;
                padding: 10px; font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {THEME['primary_hover']}, stop:1 #A78BFA);
            }}
            QPushButton:pressed {{ opacity: 0.85; }}
        """)
        layout.addWidget(self.new_btn)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background-color: {THEME['border']};")
        layout.addWidget(line)

        title = QLabel("历史对话")
        title.setStyleSheet(f"font-weight: bold; font-size: 14px; padding: 4px 0; color: {THEME['text_primary']};")
        layout.addWidget(title)

        self.conv_list = QListWidget()
        self.conv_list.setStyleSheet(f"""
            QListWidget {{
                border: 1px solid {THEME['border']}; border-radius: 8px;
                background-color: {THEME['bg_secondary']}; color: {THEME['text_primary']};
            }}
            QListWidget::item {{
                padding: 8px; border-bottom: 1px solid {THEME['border']};
                color: {THEME['text_secondary']};
            }}
            QListWidget::item:hover {{ background-color: {THEME['bg_card']}; }}
            QListWidget::item:selected {{
                background-color: {THEME['primary']}; color: white;
                border-radius: 4px;
            }}
        """)
        self.conv_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.conv_list.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.conv_list)

    def _on_context_menu(self, pos):
        """右键菜单：重命名 / 删除。"""
        item = self.conv_list.itemAt(pos)
        if not item:
            return
        conv_id = item.data(Qt.ItemDataRole.UserRole)
        if not conv_id:
            return

        menu = QMenu(self)
        rename_action = menu.addAction("重命名")
        menu.addSeparator()
        delete_action = menu.addAction("删除")

        action = menu.exec(self.conv_list.mapToGlobal(pos))
        if action == rename_action:
            self.rename_requested.emit(conv_id)
        elif action == delete_action:
            self.delete_requested.emit(conv_id)

    def clear_conversations(self):
        self.conv_list.clear()

    def add_conversation(self, title_text, preview, conv_id):
        item = QListWidgetItem(title_text)
        item.setData(Qt.ItemDataRole.UserRole, conv_id)
        self.conv_list.insertItem(0, item)


class CenterPanel(QFrame):
    """中间面板：模型选择 + 消息区 + 输入区。"""

    send_clicked = pyqtSignal(str)    # 用户点击发送（正常模式）
    stop_clicked = pyqtSignal()       # 用户点击停止（AI 回复中）
    permission_accept_clicked = pyqtSignal()
    permission_reject_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 深色主题背景
        self.setStyleSheet(f"""
            CenterPanel {{
                background-color: {THEME['bg_primary']};
            }}
        """)

        # 顶部：模型选择 + 深色主题
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        combo_style = f"""
            QComboBox {{
                background-color: {THEME['bg_input']}; color: {THEME['text_primary']};
                border: 1px solid {THEME['border']}; border-radius: 6px;
                padding: 4px 12px; font-size: 12px; min-width: 120px;
            }}
            QComboBox:hover {{ border-color: {THEME['border_focus']}; }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background-color: {THEME['bg_card']}; color: {THEME['text_primary']};
                selection-background-color: {THEME['primary']};
            }}
        """

        model_label = QLabel("模型:")
        model_label.setStyleSheet(f"color: {THEME['text_secondary']}; font-size: 12px;")
        top_bar.addWidget(model_label)

        self.model_combo = QComboBox()
        self.model_combo.addItems(["opus (最强)", "sonnet (推荐)", "haiku (最快)"])
        self.model_combo.setCurrentIndex(1)
        self.model_combo.setMinimumWidth(150)
        self.model_combo.setStyleSheet(combo_style)
        top_bar.addWidget(self.model_combo)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["普通模式", "Agent 模式 (多步骤任务)"])
        self.mode_combo.setStyleSheet(combo_style)
        top_bar.addWidget(self.mode_combo)

        perm_label = QLabel("权限:")
        perm_label.setStyleSheet(f"color: {THEME['text_secondary']}; font-size: 12px;")
        top_bar.addWidget(perm_label)

        self.permission_combo = QComboBox()
        self.permission_combo.addItems(["default(逐次询问)", "acceptEdits(自动编辑)", "plan(只读)"])
        self.permission_combo.setCurrentIndex(0)
        self.permission_combo.setMinimumWidth(170)
        self.permission_combo.setStyleSheet(combo_style)
        top_bar.addWidget(self.permission_combo)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        self._top_widgets = [top_bar.itemAt(i).widget() for i in range(top_bar.count()) if top_bar.itemAt(i).widget()]

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background-color: {THEME['border']};")
        self._separator_line = line
        layout.addWidget(line)

        # 消息区
        self.msg_scroll = QScrollArea()
        self.msg_scroll.setWidgetResizable(True)
        self.msg_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.msg_scroll.setStyleSheet(f"""
            QScrollArea {{
                border: 1px solid {THEME['border']}; border-radius: 10px;
                background: {THEME['bg_primary']};
            }}
        """)

        self.msg_container = QWidget()
        self.msg_container.setAutoFillBackground(True)
        self.msg_container.setStyleSheet(f"background-color: {THEME['bg_primary']};")
        self.msg_layout = QVBoxLayout(self.msg_container)
        self.msg_layout.setContentsMargins(4, 4, 4, 4)
        self.msg_layout.setSpacing(2)
        self.msg_layout.addStretch()
        self.msg_scroll.setWidget(self.msg_container)
        layout.addWidget(self.msg_scroll)

        # 快捷按钮行
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        btn_defs = [
            ("@ 引用文件", THEME["primary"]), ("# 智能体", THEME["green"]),
            ("! 提示词", THEME["orange"]), ("$ Skills", THEME["purple"]), (" 图片", THEME["teal"]),
        ]
        for text, color in btn_defs:
            btn = QPushButton(text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            key = text.strip().split()[0].replace("@", "ref").replace("#", "agent").replace("!", "prompt").replace("$", "skill").replace("图片", "image")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color}; color: white; border: none;
                    border-radius: 6px; padding: 4px 10px; font-size: 11px; font-weight: bold;
                }}
                QPushButton:hover {{ opacity: 0.85; }}
                QPushButton:pressed {{ opacity: 0.7; }}
            """)
            setattr(self, f"btn_{key}", btn)
            toolbar.addWidget(btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._toolbar_widgets = [toolbar.itemAt(i).widget() for i in range(toolbar.count()) if toolbar.itemAt(i).widget()]

        # 输入区
        # 权限请求条（输入框上方）
        self.permission_bar = QFrame()
        self.permission_bar.setVisible(False)
        self.permission_bar.setStyleSheet(f"""
            QFrame {{
                background-color: {THEME['bg_card']};
                border: 1px solid {THEME['border']};
                border-radius: 10px; padding: 6px;
            }}
            QLabel {{ color: {THEME['text_secondary']}; font-size: 12px; }}
        """)
        perm_layout = QHBoxLayout(self.permission_bar)
        perm_layout.setContentsMargins(10, 6, 10, 6)
        perm_layout.setSpacing(8)
        self.permission_label = QLabel("检测到权限请求")
        perm_layout.addWidget(self.permission_label)
        perm_layout.addStretch()
        self.permission_yes_btn = QPushButton("允许")
        self.permission_yes_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.permission_yes_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {THEME['green']}; color: white; border: none;
                border-radius: 8px; padding: 6px 14px; font-size: 12px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {THEME['green_hover']}; }}
        """)
        self.permission_no_btn = QPushButton("拒绝")
        self.permission_no_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.permission_no_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {THEME['red']}; color: white; border: none;
                border-radius: 8px; padding: 6px 14px; font-size: 12px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {THEME['red_hover']}; }}
        """)
        perm_layout.addWidget(self.permission_yes_btn)
        perm_layout.addWidget(self.permission_no_btn)
        layout.addWidget(self.permission_bar)

        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)

        self.input_box = QTextEdit()
        self.input_box.setPlaceholderText("输入消息...")
        self.input_box.setInputMethodHints(Qt.InputMethodHint.ImhNone)
        self.input_box.setStyleSheet(f"""
            QTextEdit {{
                border: 1px solid {THEME['border']}; border-radius: 10px;
                padding: 8px 12px; font-size: 14px;
                background-color: {THEME['bg_input']}; color: {THEME['text_primary']};
            }}
            QTextEdit:focus {{ border-color: {THEME['border_focus']}; }}
            QTextEdit::placeholder {{ color: {THEME['text_tertiary']}; }}
        """)
        self.input_box.setMinimumHeight(40)
        self.input_box.setMaximumHeight(120)
        input_layout.addWidget(self.input_box)

        self.send_btn = QPushButton("发  送")
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {THEME['primary']}, stop:1 #8B5CF6);
                color: white; border: none; border-radius: 10px;
                padding: 8px 20px; font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {THEME['primary_hover']}, stop:1 #A78BFA);
            }}
            QPushButton:disabled {{ background-color: {THEME['text_tertiary']}; }}
            QPushButton:pressed {{ opacity: 0.85; }}
        """)
        self.send_btn.setMinimumHeight(40)
        input_layout.addWidget(self.send_btn)
        layout.addLayout(input_layout)

        self._input_widgets = [input_layout.itemAt(i).widget() for i in range(input_layout.count()) if input_layout.itemAt(i).widget()]

        # 着陆页（无对话时显示，初始隐藏）
        self.landing_page = LandingPage()
        layout.addWidget(self.landing_page)

        # 默认显示着陆页
        self.show_landing()

        # 信号：按钮点击根据模式发送不同信号
        self.send_btn.clicked.connect(self._on_btn_click)
        self._is_building_response = False  # 按钮模式标记
        self.permission_yes_btn.clicked.connect(lambda: self.permission_accept_clicked.emit())
        self.permission_no_btn.clicked.connect(lambda: self.permission_reject_clicked.emit())

    def show_permission_request(self, text):
        self.permission_label.setText(text)
        self.permission_bar.setVisible(True)

    def hide_permission_request(self):
        self.permission_bar.setVisible(False)

    def set_building_response(self, building):
        """切换按钮模式：AI 回复中显示"停止"，否则显示"发送"。"""
        self._is_building_response = building
        if building:
            self.send_btn.setEnabled(True)
            self.send_btn.setText("停  止")
            self.send_btn.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {THEME['red']}, stop:1 #B91C1C);
                    color: white; border: none; border-radius: 10px;
                    padding: 8px 20px; font-size: 14px; font-weight: bold;
                }}
                QPushButton:hover {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {THEME['red_hover']}, stop:1 #991B1B);
                }}
                QPushButton:disabled {{ background-color: {THEME['text_tertiary']}; }}
                QPushButton:pressed {{ opacity: 0.85; }}
            """)
        else:
            self.send_btn.setEnabled(True)
            self.send_btn.setText("发  送")
            self.send_btn.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {THEME['primary']}, stop:1 #8B5CF6);
                    color: white; border: none; border-radius: 10px;
                    padding: 8px 20px; font-size: 14px; font-weight: bold;
                }}
                QPushButton:hover {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {THEME['primary_hover']}, stop:1 #A78BFA);
                }}
                QPushButton:disabled {{ background-color: {THEME['text_tertiary']}; }}
                QPushButton:pressed {{ opacity: 0.85; }}
            """)

    def _on_btn_click(self):
        if self._is_building_response:
            self.stop_clicked.emit()
        else:
            self._on_send()

    def _on_send(self):
        text = self.input_box.toPlainText().strip()
        if text:
            self.send_clicked.emit(text)

    def clear_messages(self):
        """清空消息区。"""
        while self.msg_layout.count() > 1:
            item = self.msg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def show_landing(self):
        """显示着陆页，带淡入动画。"""
        self.landing_page.fade_in(duration=500)
        self.msg_scroll.setVisible(False)
        self._separator_line.setVisible(False)
        for w in self._toolbar_widgets:
            w.setVisible(False)
        for w in self._input_widgets:
            w.setVisible(False)

    def hide_landing(self):
        """隐藏着陆页，带淡出动画。"""
        def on_finished():
            self.landing_page.setVisible(False)
            self.landing_page._opacity_effect.setOpacity(1.0)
        self.landing_page.fade_out(duration=300, callback=on_finished)
        self.msg_scroll.setVisible(True)
        self._separator_line.setVisible(True)
        for w in self._toolbar_widgets:
            w.setVisible(True)
        for w in self._input_widgets:
            w.setVisible(True)

    def _animate_widget_in(self, widget, duration=400):
        """给新添加的 widget 加淡入动画。

        避免在布局更新期间设置 QGraphicsEffect，使用 QTimer 延迟启动。
        """
        from PyQt6.QtWidgets import QGraphicsOpacityEffect

        # 先完全隐藏
        widget.setVisible(False)

        def _start_fade():
            """延迟一帧后启动淡入动画。"""
            widget.setVisible(True)
            effect = QGraphicsOpacityEffect(widget)
            effect.setOpacity(0.0)
            widget.setGraphicsEffect(effect)

            anim = QPropertyAnimation(effect, b"opacity")
            anim.setDuration(duration)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)

            # 保存引用，避免 GC
            widget._fade_anim = anim
            widget._fade_effect = effect

            def on_finished():
                # 动画结束后移除 effect，避免长期占用 paint 管线
                if widget is not None and widget.graphicsEffect() is effect:
                    widget.setGraphicsEffect(None)
                    widget._fade_effect = None

            anim.finished.connect(on_finished)
            anim.start()

        # 延迟 50ms 启动动画，避免与 paint 事件冲突
        QTimer.singleShot(50, _start_fade)

    def add_message(self, role, text):
        """添加消息到聊天区，带淡入动画。"""
        row = MessageRow(role, text)
        spring_index = self.msg_layout.count() - 1
        self.msg_layout.insertWidget(spring_index, row)
        self._animate_widget_in(row)
        self._scroll_to_bottom()
        return row

    def _find_latest_thinking_row(self):
        if self.msg_layout.count() <= 1:
            return None
        for i in range(self.msg_layout.count() - 2, -1, -1):
            item = self.msg_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), ThinkingRow):
                return item.widget()
            if item and item.widget() and isinstance(item.widget(), MessageRow):
                break
        return None

    def add_thinking_block(self, text, duration_ms, in_progress=True):
        """添加或更新当前轮次思考块。"""
        row = self._find_latest_thinking_row()
        if row is None:
            row = ThinkingRow(text, duration_ms)
            spring_index = self.msg_layout.count() - 1
            self.msg_layout.insertWidget(spring_index, row)
            self._animate_widget_in(row)
        else:
            row.append_thinking(text, duration_ms)
        row.set_in_progress(in_progress)
        self._scroll_to_bottom()
        return row

    def set_thinking_block_state(self, in_progress):
        """更新当前轮次思考块状态。"""
        row = self._find_latest_thinking_row()
        if row:
            row.set_in_progress(in_progress)

    def _scroll_to_bottom(self):
        QTimer.singleShot(50, lambda: self.msg_scroll.verticalScrollBar().setValue(
            self.msg_scroll.verticalScrollBar().maximum()
        ))

    def remove_thinking_placeholder(self):
        """移除最后的占位消息（"思考中..."）。"""
        if self.msg_layout.count() <= 1:
            return
        for i in range(self.msg_layout.count() - 2, -1, -1):
            item = self.msg_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), MessageRow):
                widget = item.widget()
                # 检查是否是 assistant 的占位消息
                if widget.role == "assistant":
                    text = widget._content_label.text()
                    if "思考中" in text:
                        self.msg_layout.removeWidget(widget)
                        widget.deleteLater()
                break

    def update_last_message(self, text):
        """更新最后一条消息（用于流式输出）。"""
        if self.msg_layout.count() <= 1:
            return
        for i in range(self.msg_layout.count() - 2, -1, -1):
            item = self.msg_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), MessageRow):
                widget = item.widget()
                widget.update_text(text)
                # 直接滚动
                self.msg_scroll.verticalScrollBar().setValue(
                    self.msg_scroll.verticalScrollBar().maximum()
                )
                break

    def update_processing_status(self, text):
        """更新处理中状态文案（不产生新气泡）。"""
        if not text:
            return
        self.update_last_message(f"处理中：{text}")

    def get_last_message_text(self):
        """获取最后一条消息文本。"""
        if self.msg_layout.count() <= 1:
            return ""
        for i in range(self.msg_layout.count() - 2, -1, -1):
            item = self.msg_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), MessageRow):
                return item.widget().get_text()
        return ""


class RightPanel(QFrame):
    """右侧面板：项目文件树 + 文件变更。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(220)
        self.setStyleSheet(f"""
            RightPanel {{
                background-color: {THEME['bg_secondary']};
                border-left: 1px solid {THEME['border']};
            }}
        """)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(6)

        title = QLabel("项目文件")
        title.setStyleSheet(f"font-weight: bold; font-size: 14px; padding: 4px 0; color: {THEME['text_primary']};")
        layout.addWidget(title)

        self.file_list = QListWidget()
        self.file_list.setStyleSheet(f"""
            QListWidget {{
                border: 1px solid {THEME['border']}; border-radius: 8px;
                background-color: {THEME['bg_secondary']}; color: {THEME['text_secondary']};
            }}
            QListWidget::item {{ padding: 4px 8px; color: {THEME['text_secondary']}; }}
            QListWidget::item:selected {{ background-color: {THEME['primary']}; color: white; }}
        """)
        self.file_list.setPalette(QApplication.instance().palette())
        layout.addWidget(self.file_list)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background-color: {THEME['border']};")
        layout.addWidget(line)

        change_title = QLabel("文件变更")
        change_title.setStyleSheet(f"font-weight: bold; font-size: 14px; padding: 4px 0; color: {THEME['text_primary']};")
        layout.addWidget(change_title)

        self.change_list = QListWidget()
        self.change_list.setStyleSheet(f"""
            QListWidget {{
                border: 1px solid {THEME['border']}; border-radius: 8px;
                background-color: {THEME['bg_secondary']}; color: {THEME['text_secondary']};
            }}
            QListWidget::item {{ padding: 4px 8px; color: {THEME['text_secondary']}; }}
        """)
        item = QListWidgetItem("暂无变更")
        item.setForeground(QColor(THEME['text_tertiary']))
        self.change_list.addItem(item)
        layout.addWidget(self.change_list)


# ==================== 主窗口 ====================

class MainWindow(QMainWindow):
    """主窗口。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Claude Code 桌面助手")
        # 启动时最大化窗口
        self.showMaximized()
        self.setMinimumSize(900, 500)

        # 深色主题窗口背景
        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {THEME['bg_primary']}; }}
        """)

        self.claude_client = ClaudeClient()
        self.current_conv_id = None
        self._building_response = False
        self._pending_session_id = None
        self._is_first_send = False
        self._session_last_active = None  # session 最后活跃时间
        self._SESSION_TIMEOUT = 1800  # session 超时阈值（秒），30 分钟
        self._last_thinking_segments = []  # 当前轮次思考分段
        self._has_stream_text = False  # 当前轮次是否已收到正文流
        self._permission_prompt_shown = False  # 当前轮次是否已弹出权限提示
        self._hook_token = None
        self._hook_server = None
        self._hook_server_thread = None
        self._pending_permission = None  # {event, done_event, decision}
        self._stop_pending = False  # 用户主动停止标记
        self._pending_new_conv_id = None  # 新建但未发送的对话 ID

        self._build()
        QTimer.singleShot(300, self._init_content)
        self._start_permission_hook_server()

        # 后台 git 工作线程
        self._worker_thread = QThread()
        self.git_worker = GitWorker()
        self.git_worker.moveToThread(self._worker_thread)
        self.git_worker.files_ready.connect(self._on_files_ready)
        self.git_worker.status_ready.connect(self._on_status_ready)
        self._worker_thread.start()

        # 定时刷新
        self.change_timer = QTimer()
        self.change_timer.timeout.connect(self._schedule_git_status)
        self.change_timer.start(8000)

        # session 超时检查定时器（每 60 秒检查一次）
        self._session_check_timer = QTimer()
        self._session_check_timer.timeout.connect(self._check_session_timeout)
        self._session_check_timer.start(60000)

    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        self.left_panel = LeftPanel()
        self.center_panel = CenterPanel()
        self.right_panel = RightPanel()

        main_layout.addWidget(self.left_panel)
        main_layout.addWidget(self.center_panel)
        main_layout.addWidget(self.right_panel)

        # 信号绑定
        self.center_panel.send_clicked.connect(self._on_send)
        self.center_panel.stop_clicked.connect(self._on_stop)
        self.center_panel.permission_accept_clicked.connect(self._on_permission_accept)
        self.center_panel.permission_reject_clicked.connect(self._on_permission_reject)
        self.center_panel.input_box.keyPressEvent = self._input_key_press
        self.left_panel.new_btn.clicked.connect(self._new_conversation)
        self.left_panel.conv_list.itemClicked.connect(self._on_select_conversation)
        self.left_panel.rename_requested.connect(self._on_rename_requested)
        self.left_panel.delete_requested.connect(self._on_delete_requested)
        self.center_panel.btn_ref.clicked.connect(self._insert_at)
        self.center_panel.btn_agent.clicked.connect(self._insert_hash)
        self.center_panel.btn_prompt.clicked.connect(self._insert_bang)
        self.center_panel.btn_skill.clicked.connect(self._insert_dollar)
        self.center_panel.btn_image.clicked.connect(self._upload_image)
        # 着陆页发送信号
        self.center_panel.landing_page.send_clicked.connect(self._on_landing_send)

    def _init_content(self):
        self._load_saved_conversations()
        self._schedule_git_files()
        self._schedule_git_status()
        # 无对话时显示着陆页
        if not self.current_conv_id:
            self.center_panel.show_landing()

    def _load_saved_conversations(self):
        self.left_panel.clear_conversations()
        convs = list_conversations()
        for conv in convs:
            preview = ""
            for msg in conv.get("messages", []):
                if msg.get("role") == "user":
                    preview = msg.get("content", "")[:40]
                    break
            self.left_panel.add_conversation(conv["title"], preview, conv["id"])

        if convs:
            self._select_conversation(convs[0]["id"])

    def _select_conversation(self, conv_id):
        if self._building_response:
            QMessageBox.warning(self, "提示", "请等待当前对话完成")
            return

        conv = load_conversation(conv_id)
        if not conv:
            return

        self.current_conv_id = conv_id
        self._is_first_send = False
        # 切换到其他对话，清除 pending 标记
        if conv.get("title") != "新增对话":
            self._pending_new_conv_id = None
        self.center_panel.clear_messages()
        self.center_panel.hide_landing()

        for msg in conv.get("messages", []):
            role = msg.get("role", "user")
            text = msg.get("content", "")
            if role == "system":
                continue
            self.center_panel.add_message(role, text)
            # 如果有 thinking 信息，在 AI 消息后面恢复思考块
            if role == "assistant" and "thinking" in msg:
                segments = msg.get("thinking_segments")
                if segments and isinstance(segments, list):
                    for seg in segments:
                        self.center_panel.add_thinking_block(seg.get("text", ""), seg.get("duration_ms", 0), in_progress=False)
                else:
                    thinking_text = msg["thinking"]
                    thinking_ms = msg.get("thinking_duration_ms", 0)
                    self.center_panel.add_thinking_block(thinking_text, thinking_ms, in_progress=False)

        # 高亮左侧列表项
        for i in range(self.left_panel.conv_list.count()):
            item = self.left_panel.conv_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == conv_id:
                self.left_panel.conv_list.setCurrentItem(item)
                break

    def _on_select_conversation(self, item):
        conv_id = item.data(Qt.ItemDataRole.UserRole)
        if conv_id:
            self._select_conversation(conv_id)

    def _schedule_git_files(self):
        from PyQt6.QtCore import QMetaObject
        QMetaObject.invokeMethod(self.git_worker, "fetch_files", Qt.ConnectionType.QueuedConnection)

    def _schedule_git_status(self):
        from PyQt6.QtCore import QMetaObject
        QMetaObject.invokeMethod(self.git_worker, "fetch_status", Qt.ConnectionType.QueuedConnection)

    def _on_files_ready(self, files):
        self.right_panel.file_list.clear()
        if files:
            for f in files:
                self.right_panel.file_list.addItem(f)
        else:
            self.right_panel.file_list.addItem("（未找到 git 仓库）")

    def _on_status_ready(self, status):
        self.right_panel.change_list.clear()
        has_changes = False
        for path in status.get("modified", []):
            has_changes = True
            item = QListWidgetItem(f"[已修改] {path}")
            item.setForeground(QColor("#F97316"))
            self.right_panel.change_list.addItem(item)
        for path in status.get("added", []):
            has_changes = True
            item = QListWidgetItem(f"[已新增] {path}")
            item.setForeground(QColor("#22C55E"))
            self.right_panel.change_list.addItem(item)
        for path in status.get("deleted", []):
            has_changes = True
            item = QListWidgetItem(f"[已删除] {path}")
            item.setForeground(QColor("#EF4444"))
            self.right_panel.change_list.addItem(item)
        if not has_changes:
            self.right_panel.change_list.addItem("暂无变更")

    def _input_key_press(self, event):
        """Enter 发送，Shift+Enter 换行。"""
        if event.key() == Qt.Key.Key_Return and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self._on_send()
            return
        QTextEdit.keyPressEvent(self.center_panel.input_box, event)

    def _on_landing_send(self, text):
        """从着陆页发送消息：创建新对话并发送。"""
        if self._building_response:
            return
        # 创建新对话
        self._new_conversation(silent=True)
        # 用着陆页的文本发送
        self.center_panel.input_box.setText(text)
        self._on_send()

    def _on_send(self):
        """发送消息。"""
        if self._building_response:
            return

        text = self.center_panel.input_box.toPlainText().strip()
        if not text:
            return
        self.center_panel.input_box.clear()

        if not self.current_conv_id:
            self._new_conversation(silent=True)

        # 检查 session 是否超时，如果超时则清空 session_id
        if self._session_last_active:
            elapsed = (datetime.now() - self._session_last_active).total_seconds()
            if elapsed > self._SESSION_TIMEOUT:
                # session 已超时，清空 session_id，创建新 session
                conv = load_conversation(self.current_conv_id)
                if conv and conv.get("session_id"):
                    conv["session_id"] = None
                    save_conversation(self.current_conv_id, conv.get("title", ""), conv.get("messages", []), session_id=None)
                    print(f"[Session] session 已超时（{elapsed:.0f}秒），清空 session_id")
                self._session_last_active = None

        conv_id = self.current_conv_id
        conv = load_conversation(conv_id)
        if not conv:
            return
        messages = conv.get("messages", [])

        # 标记是否首次发送：已有对话但 messages 为空 = 第一次发消息
        is_first = (len(messages) == 0)
        if is_first:
            self._is_first_send = True

        # 添加并显示用户消息
        messages.append({"role": "user", "content": text})
        self.center_panel.add_message("user", text)

        save_conversation(conv_id, conv.get("title", "新增对话"), messages)

        # 更新按钮为停止模式
        self.center_panel.set_building_response(True)
        self._building_response = True

        # 添加 AI 占位消息（带表情 + 动画）
        self.center_panel.add_message("assistant", "🤔 思考中...")
        self._last_thinking_segments = []
        self._has_stream_text = False
        self._permission_prompt_shown = False

        # 获取当前对话的 session_id（用于续接历史对话）
        session_id = conv.get("session_id") if conv else None
        self._pending_session_id = None  # 重置 pending

        # 构建对话上下文（只取最后一条用户消息，历史由 Claude session 管理）
        prompt = self.claude_client.build_prompt(messages)
        model_name = self.center_panel.model_combo.currentText()
        model = {"opus (最强)": "opus", "sonnet (推荐)": "sonnet", "haiku (最快)": "haiku"}.get(model_name, "sonnet")
        perm_ui = self.center_panel.permission_combo.currentText()
        permission_mode = "default"
        if perm_ui.startswith("acceptEdits"):
            permission_mode = "acceptEdits"
        elif perm_ui.startswith("plan"):
            permission_mode = "plan"

        # 创建 Claude 工作线程
        self._claude_thread = QThread()
        self._claude_worker = ClaudeWorker(prompt, model, session_id=session_id, permission_mode=permission_mode)
        self._claude_worker.moveToThread(self._claude_thread)
        self._claude_worker.chunk_ready.connect(self._on_chunk)
        self._claude_worker.result_ready.connect(self._on_claude_result)
        self._claude_worker.session_ready.connect(self._on_session_ready)
        self._claude_worker.thinking_started.connect(self._on_thinking_started)
        self._claude_worker.thinking_ready.connect(self._on_thinking_ready)
        self._claude_worker.status_update.connect(self._on_worker_status)
        self._claude_worker.error_occurred.connect(self._on_claude_error)
        self._claude_worker.stopped.connect(self._on_worker_stopped)
        self._claude_thread.finished.connect(self._on_claude_thread_done)
        self._claude_thread.started.connect(self._claude_worker.run)
        self._claude_thread.start()

    def _on_session_ready(self, session_id):
        """收到 Claude 的 session_id（新对话首次创建）。"""
        self._pending_session_id = session_id

    def _on_thinking_started(self):
        """Claude 开始思考。"""
        self.center_panel.add_thinking_block("", 0, in_progress=True)
        if not self._has_stream_text:
            self.center_panel.update_processing_status("正在深度思考")

    def _on_thinking_ready(self, text, duration_ms):
        """收到一段完整思考内容。"""
        entry = {"text": text, "duration_ms": int(duration_ms or 0)}
        self._last_thinking_segments.append(entry)
        self.center_panel.add_thinking_block(text, duration_ms, in_progress=True)

    def _on_worker_status(self, status_text):
        """更新过程态状态，避免界面看起来无响应。"""
        if not self._has_stream_text:
            self.center_panel.update_processing_status(status_text)

    def _on_claude_result(self, result):
        """Claude 执行完成。"""
        self._claude_thread.quit()
        self._claude_thread.wait(1000)
        self._building_response = False
        self._session_last_active = datetime.now()  # 更新活跃时间
        print(f"[Title] _on_claude_result, _is_first_send={self._is_first_send}, conv_id={self.current_conv_id}")
        self._finish_response(result)

    def _on_claude_error(self, error_msg):
        """Claude 执行出错。"""
        self._claude_thread.quit()
        self._claude_thread.wait(1000)
        self._building_response = False
        # 检测 session 相关错误（超时 / 超过最大 session 数）
        error_lower = error_msg.lower()
        if "session" in error_lower or "max" in error_lower or "limit" in error_lower or "timeout" in error_lower or "expire" in error_lower:
            # session 已失效，清空 session_id，下次发送时自动创建新 session
            if self.current_conv_id:
                conv = load_conversation(self.current_conv_id)
                if conv and conv.get("session_id"):
                    conv["session_id"] = None
                    save_conversation(self.current_conv_id, conv.get("title", ""), conv.get("messages", []), session_id=None)
                    print(f"[Session] 检测到 session 过期，已清空 session_id")
        self._handle_error(error_msg)

    def _on_worker_stopped(self):
        """ClaudeWorker 被用户主动终止——只退出线程，清理在 _on_claude_thread_done 统一处理。"""
        print(f"[Stop] Worker 已停止，等待线程退出")
        self._claude_thread.quit()

    def _on_claude_thread_done(self):
        """ClaudeWorker 线程已结束——统一清理入口。"""
        if self._stop_pending:
            # 用户主动终止，执行停止清理
            self._stop_pending = False
            print(f"[Stop] 执行停止清理")
            self._on_stop_cleanup()
        elif self._building_response:
            # 非正常完成（非 result、非 error），也做停止清理
            print(f"[Stop] 线程异常退出，执行清理")
            self._on_stop_cleanup()

    def _on_stop_cleanup(self):
        """停止后的清理工作。"""
        if not self._building_response:
            return  # 已经清理过了
        self._building_response = False
        self._last_thinking_segments = []
        self.center_panel.set_building_response(False)
        self.center_panel.set_thinking_block_state(False)
        # 移除最后的"思考中..."占位消息
        self.center_panel.remove_thinking_placeholder()

    def _on_chunk(self, text):
        """收到 AI 的流式回复片段（主线程）。"""
        self._has_stream_text = True
        self.center_panel.update_last_message(text)
        if self._looks_like_permission_prompt(text):
            self._show_permission_prompt(text)

    def _on_done(self, full_text):
        """AI 回复完成（子线程）。"""
        self._building_response = False
        self._finish_response(full_text)

    @staticmethod
    def _looks_like_permission_prompt(text):
        if not text:
            return False
        candidates = [
            "需要你的权限",
            "请批准",
            "批准这次编辑",
            "approve",
            "permission",
        ]
        lower_text = text.lower()
        for c in candidates:
            if c.lower() in lower_text:
                return True
        return False

    def _show_permission_prompt(self, text):
        """权限请求提示：内嵌到输入框上方（更自然）。"""
        if self._permission_prompt_shown:
            return
        self._permission_prompt_shown = True
        # 这是“文本级提示”兜底；真实权限由 PermissionRequest hook 触发并驱动 UI
        self.center_panel.show_permission_request("需要权限继续（若系统未弹出审批条，请检查 hooks 是否启用）")

    def _on_permission_accept(self):
        """用户允许权限：如果是 hook 权限请求则回写决策；否则按文本级继续处理。"""
        if self._pending_permission:
            self._pending_permission["decision"] = {"behavior": "allow"}
            print("[Permission] GUI allow")
            self._pending_permission["done_event"].set()
            self.center_panel.hide_permission_request()
            return
        self.center_panel.hide_permission_request()
        # 让 AI “收到” 继续指令：直接作为用户消息发送
        self.center_panel.input_box.setText("可以编辑，请继续")
        self._on_send()

    def _on_permission_reject(self):
        """用户拒绝权限：如果是 hook 权限请求则回写拒绝；否则只隐藏提示。"""
        if self._pending_permission:
            self._pending_permission["decision"] = {"behavior": "deny", "message": "用户在 GUI 中拒绝了该操作", "interrupt": False}
            print("[Permission] GUI deny")
            self._pending_permission["done_event"].set()
            self.center_panel.hide_permission_request()
            return
        self.center_panel.hide_permission_request()

    def _start_permission_hook_server(self):
        """启动本地 HTTP server，供 Claude Code PermissionRequest hook 回调。"""
        try:
            project_dir = os.path.dirname(os.path.abspath(__file__))
            claude_dir = os.path.join(project_dir, ".claude")
            os.makedirs(claude_dir, exist_ok=True)

            token = secrets.token_hex(16)
            self._hook_token = token

            window = self

            class Handler(BaseHTTPRequestHandler):
                def _send_json(self, code, payload):
                    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                    self.send_response(code)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def do_POST(self):
                    if self.path != "/permission":
                        return self._send_json(404, {"error": "not_found"})
                    auth = self.headers.get("X-CCVIEW-TOKEN", "")
                    if not auth or auth != window._hook_token:
                        return self._send_json(401, {"error": "unauthorized"})
                    length = int(self.headers.get("Content-Length", "0") or "0")
                    raw = self.rfile.read(length) if length > 0 else b"{}"
                    try:
                        event = json.loads(raw.decode("utf-8"))
                    except Exception:
                        return self._send_json(400, {"error": "bad_json"})

                    done = threading.Event()
                    pending = {"event": event, "done_event": done, "decision": None}
                    window._pending_permission = pending
                    print(f"[Permission] request tool={event.get('tool_name')} mode={event.get('permission_mode')}")

                    tool_name = event.get("tool_name", "")
                    tool_input = event.get("tool_input", {})
                    summary = f"权限申请：{tool_name}"
                    if tool_name == "Bash" and isinstance(tool_input, dict):
                        cmd = tool_input.get("command", "")
                        if cmd:
                            summary = f"权限申请：运行命令\n{cmd}"
                    elif tool_name in ("Write", "Edit") and isinstance(tool_input, dict):
                        fp = tool_input.get("file_path", "") or tool_input.get("path", "")
                        if fp:
                            summary = f"权限申请：修改文件\n{fp}"

                    # 通过 Qt 主线程更新 UI
                    QTimer.singleShot(0, lambda: window.center_panel.show_permission_request(summary))

                    # 阻塞等待用户点击（最长 10 分钟）
                    if not done.wait(timeout=600):
                        window._pending_permission = None
                        QTimer.singleShot(0, lambda: window.center_panel.hide_permission_request())
                        return self._send_json(200, {"behavior": "deny", "message": "权限请求超时未响应", "interrupt": False})

                    decision = pending.get("decision") or {"behavior": "allow"}
                    print(f"[Permission] respond {decision}")
                    window._pending_permission = None
                    QTimer.singleShot(0, lambda: window.center_panel.hide_permission_request())
                    return self._send_json(200, decision)

                def log_message(self, format, *args):
                    return  # 静默

            # 用动态端口
            server = HTTPServer(("127.0.0.1", 0), Handler)
            self._hook_server = server
            port = server.server_address[1]

            # 写出给 hook 读取
            hook_info_path = os.path.join(claude_dir, "cc_view_hook.json")
            with open(hook_info_path, "w", encoding="utf-8") as f:
                json.dump({"port": port, "token": token}, f, ensure_ascii=False, indent=2)

            def serve():
                try:
                    server.serve_forever()
                except Exception:
                    pass

            th = threading.Thread(target=serve, daemon=True)
            th.start()
            self._hook_server_thread = th
        except Exception as e:
            print(f"[HookServer] 启动失败: {e}")

    def _finish_response(self, full_text):
        """在主线程完成回复处理。"""
        self.center_panel.set_thinking_block_state(False)

        # 多轮 tool_use 场景下，result 可能只含最后一段文本。
        # 若流式阶段已显示更完整内容，优先保留更完整版本，避免被覆盖。
        displayed_text = self.center_panel.get_last_message_text()
        final_text = full_text or ""
        if displayed_text and len(displayed_text.strip()) > len(final_text.strip()):
            final_text = displayed_text

        self.center_panel.update_last_message(final_text)
        if self._looks_like_permission_prompt(final_text):
            self._show_permission_prompt(final_text)
        self._session_last_active = datetime.now()  # 更新活跃时间

        if self.current_conv_id:
            conv = load_conversation(self.current_conv_id)
            if conv:
                messages = conv.get("messages", [])
                # 保存 assistant 消息，带上 thinking 信息
                assistant_msg = {"role": "assistant", "content": final_text}
                if self._last_thinking_segments:
                    thinking_text = "\n\n".join(
                        f"[第{idx}段 | 用时 {seg.get('duration_ms', 0)}毫秒]\n{seg.get('text', '')}"
                        for idx, seg in enumerate(self._last_thinking_segments, start=1)
                    )
                    thinking_ms = sum(max(0, int(seg.get("duration_ms", 0))) for seg in self._last_thinking_segments)
                    assistant_msg["thinking"] = thinking_text
                    assistant_msg["thinking_duration_ms"] = thinking_ms
                    assistant_msg["thinking_segments"] = self._last_thinking_segments
                    self._last_thinking_segments = []  # 消费后清空
                messages.append(assistant_msg)
                session_id = self._pending_session_id or conv.get("session_id")

                if self._is_first_send:
                    # 首次发送：先保存规则生成的临时标题，再后台调用 AI 生成
                    temp_title = self._generate_title(final_text)
                    save_conversation(self.current_conv_id, temp_title, messages, session_id)
                    self._is_first_send = False
                    self._pending_new_conv_id = None  # 已发送，清除 pending
                    self._refresh_sidebar_preview()
                    # 后台 AI 生成标题（不阻塞 UI）
                    self._start_ai_title_generation(final_text)
                else:
                    save_conversation(self.current_conv_id, conv.get("title", "新增对话"), messages, session_id)

                self._pending_session_id = None

        self.center_panel.set_building_response(False)

    def _generate_title(self, ai_text):
        """规则生成临时标题——优先用用户第一条消息的关键词。"""
        # 优先取用户第一条消息
        if self.current_conv_id:
            conv = load_conversation(self.current_conv_id)
            if conv:
                for msg in conv.get("messages", []):
                    if msg.get("role") == "user":
                        text = msg.get("content", "").strip()
                        # 去掉特殊前缀（@ # ! $ 等命令符）
                        cleaned = text.lstrip("@#!$").strip()
                        # 如果用户消息很短（<6字），结合 AI 回复
                        if len(cleaned) < 6:
                            break
                        # 提取关键词：去掉常见无意义前缀
                        prefixes = ["请问", "帮我", "请帮我", "帮我写", "请写", "能不能", "如何", "为什么", "什么是", "解释一下", "分析一下"]
                        for p in prefixes:
                            if cleaned.startswith(p):
                                cleaned = cleaned[len(p):]
                                break
                        cleaned = cleaned.strip()
                        # 截断到 12 字
                        if len(cleaned) > 12:
                            return cleaned[:12] + "…"
                        return cleaned if cleaned else text
                        break
        # 降级：用 AI 回复的第一行关键词
        if ai_text and ai_text.strip():
            first_line = ai_text.strip().split("\n")[0].strip()
            # 去掉 markdown 符号
            first_line = first_line.lstrip("#*`- ").strip()
            if len(first_line) > 12:
                return first_line[:12] + "…"
            return first_line
        return "新增对话"

    def _start_ai_title_generation(self, ai_reply):
        """后台调用 AI 生成标题，失败自动降级。"""
        print(f"[Title] 开始 AI 标题生成，conv_id={self.current_conv_id}")
        # 获取用户第一条消息
        user_msg = ""
        conv = load_conversation(self.current_conv_id)
        if conv:
            for msg in conv.get("messages", []):
                if msg.get("role") == "user":
                    user_msg = msg.get("content", "")
                    break

        if not user_msg and not ai_reply:
            return

        self._title_worker = TitleWorker(user_msg, ai_reply)
        self._title_worker.title_ready.connect(self._on_title_ready)
        self._title_worker.finished.connect(self._on_title_worker_done)
        self._title_worker.start()

    def _on_title_ready(self, title):
        """AI 标题生成完成。"""
        print(f"[Title] AI 标题: '{title}'")
        if title and len(title) > 0 and self.current_conv_id:
            # 截断到 12 字
            if len(title) > 12:
                title = title[:12] + "…"
            conv = load_conversation(self.current_conv_id)
            if conv:
                # 用 AI 生成的标题替换当前标题（无论是否默认值）
                save_conversation(self.current_conv_id, title, conv.get("messages", []), conv.get("session_id"))
                self._refresh_sidebar_preview()
                print(f"[Title] AI 生成标题: {title}")

    def _on_title_worker_done(self):
        """TitleWorker 线程完成——无论成功失败都到此。"""
        print(f"[Title] TitleWorker 线程完成")

    def _on_stop(self):
        """用户主动终止 AI 回复。"""
        if not self._building_response or not hasattr(self, '_claude_worker'):
            return
        self._stop_pending = True
        self._claude_worker.stop()
        print(f"[Stop] 已终止 Claude 回复")

    def _handle_error(self, error_msg):
        self.center_panel.update_last_message(f"[出错] {error_msg}")
        self.center_panel.set_building_response(False)
        self.center_panel.set_thinking_block_state(False)
        self._last_thinking_segments = []

    def _check_session_timeout(self):
        """定时检查 session 是否超时。"""
        if not self._session_last_active or not self.current_conv_id:
            return
        elapsed = (datetime.now() - self._session_last_active).total_seconds()
        if elapsed > self._SESSION_TIMEOUT:
            conv = load_conversation(self.current_conv_id)
            if conv and conv.get("session_id"):
                conv["session_id"] = None
                save_conversation(self.current_conv_id, conv.get("title", ""), conv.get("messages", []), session_id=None)
                print(f"[Session] 定时检查发现 session 超时（{elapsed:.0f}秒），已清空 session_id")
            self._session_last_active = None

    def _refresh_sidebar_preview(self):
        """只刷新侧边栏预览，不清空消息区。"""
        self.left_panel.clear_conversations()
        convs = list_conversations()
        for conv in convs:
            preview = ""
            for msg in conv.get("messages", []):
                if msg.get("role") == "user":
                    preview = msg.get("content", "")[:40]
                    break
            self.left_panel.add_conversation(conv["title"], preview, conv["id"])

        # 高亮当前对话
        if self.current_conv_id:
            for i in range(self.left_panel.conv_list.count()):
                item = self.left_panel.conv_list.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == self.current_conv_id:
                    self.left_panel.conv_list.setCurrentItem(item)
                    break

    def _on_rename_requested(self, conv_id):
        """右键 → 重命名。"""
        conv = load_conversation(conv_id)
        if not conv:
            return
        old_title = conv.get("title", "未命名")
        new_title, ok = QInputDialog.getText(self, "重命名对话", "新标题：", text=old_title)
        if ok and new_title.strip():
            messages = conv.get("messages", [])
            save_conversation(conv_id, new_title.strip(), messages, conv.get("session_id"))
            self._refresh_sidebar_preview()

    def _on_delete_requested(self, conv_id):
        """右键 → 删除。"""
        if self._building_response:
            QMessageBox.warning(self, "提示", "请等待当前对话完成")
            return

        conv = load_conversation(conv_id)
        if not conv:
            return
        title = conv.get("title", "未命名")
        reply = QMessageBox.question(
            self, "确认删除", f"确定要删除对话「{title}」吗？\n此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # 删除文件
        filepath = os.path.join(DATA_DIR, f"{conv_id}.json")
        if os.path.exists(filepath):
            os.remove(filepath)

        # 如果删除的是当前对话，切换或清空
        if self.current_conv_id == conv_id:
            self.current_conv_id = None
            self._pending_session_id = None
            if self._pending_new_conv_id == conv_id:
                self._pending_new_conv_id = None
            # 尝试选中相邻对话
            convs = list_conversations()
            if convs:
                self._select_conversation(convs[0]["id"])
            else:
                self.center_panel.show_landing()

        self._refresh_sidebar_preview()

    def _new_conversation(self, silent=False):
        if self._building_response:
            QMessageBox.warning(self, "提示", "请等待当前对话完成")
            return

        # 如果已有未发送的「新增对话」，直接跳转不新建
        if self._pending_new_conv_id:
            pending = load_conversation(self._pending_new_conv_id)
            if pending and pending.get("title") == "新增对话":
                self.current_conv_id = self._pending_new_conv_id
                self.center_panel.hide_landing()
                self.center_panel.clear_messages()
                if not silent:
                    self._refresh_sidebar_preview()
                return

        conv_id = str(uuid.uuid4())[:8]
        title = "新增对话"
        save_conversation(conv_id, title, [], session_id=None)
        self._pending_new_conv_id = conv_id
        self.current_conv_id = conv_id
        self._pending_session_id = None
        self._is_first_send = False
        self._session_last_active = None
        self.center_panel.hide_landing()
        self.center_panel.clear_messages()

        if not silent:
            self._refresh_sidebar_preview()

    def _insert_at(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "选择要引用的文件")
        if filepath:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read(2000)
                self.center_panel.input_box.setText(f"[引用: {os.path.basename(filepath)}] {content[:200]}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法读取文件: {e}")

    def _insert_hash(self):
        popup = PopupList("选择智能体", AGENT_LIST, self)
        if popup.exec() and popup.selected:
            self.center_panel.input_box.insertPlainText(f" #{popup.selected} ")

    def _insert_bang(self):
        items = [(n, t) for n, t in PROMPT_TEMPLATES.items()]
        popup = PopupList("插入提示词模板", items, self)
        if popup.exec() and popup.selected:
            self.center_panel.input_box.setText(popup.selected)

    def _insert_dollar(self):
        popup = PopupList("调用 Skills", SKILLS_LIST, self)
        if popup.exec() and popup.selected:
            self.center_panel.input_box.insertPlainText(f" /{popup.selected} ")

    def _upload_image(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择图片", "", "图片文件 (*.png *.jpg *.jpeg *.gif *.webp);;所有文件 (*.*)"
        )
        if filepath:
            self.center_panel.add_message("user", f"[已上传图片: {os.path.basename(filepath)}]")

    def closeEvent(self, event):
        # 停止本地权限 hook server
        try:
            if getattr(self, "_hook_server", None):
                self._hook_server.shutdown()
        except Exception:
            pass
        # 终止 ClaudeWorker 子线程
        if hasattr(self, '_claude_thread') and self._claude_thread.isRunning():
            self._claude_thread.quit()
            self._claude_thread.wait(2000)
        # 终止标题生成线程
        if hasattr(self, '_title_worker') and self._title_worker.isRunning():
            self._title_worker.terminate()
            self._title_worker.wait(2000)
        self.claude_client.stop()
        self._worker_thread.quit()
        self._worker_thread.wait(2000)
        super().closeEvent(event)


def main():
    # 检查 claude CLI 是否已安装
    if subprocess.call(["claude", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
        print("错误: 未找到 claude 命令。")
        print("请先安装 Claude Code: https://docs.anthropic.com/zh-CN/docs/claude-code/CLI")
        sys.exit(1)

    app = QApplication([])
    app.setApplicationName("Claude Code 桌面助手")
    # 设置窗口图标
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "image", "ico.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    # 全局深色滚动条样式
    scrollbar_w = 8
    scrollbar_c = THEME.get('border_focus', '#6366F1')
    scrollbar_bg = THEME.get('bg_primary', '#0F0F14')
    app.setStyleSheet(f"""
        QScrollBar:vertical {{
            background: {scrollbar_bg}; width: {scrollbar_w}px;
            border-radius: 4px; margin: 0px;
        }}
        QScrollBar::handle:vertical {{
            background: #3D3D5C; border-radius: 4px;
            min-height: 20px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {scrollbar_c};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
        QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical,
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: none; border: none;
        }}
        QScrollBar:horizontal {{
            background: {scrollbar_bg}; height: {scrollbar_w}px;
            border-radius: 4px; margin: 0px;
        }}
        QScrollBar::handle:horizontal {{
            background: #3D3D5C; border-radius: 4px;
            min-width: 20px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {scrollbar_c};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
        QScrollBar::left-arrow:horizontal, QScrollBar::right-arrow:horizontal,
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: none; border: none;
        }}
    """)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
