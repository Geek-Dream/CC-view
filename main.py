#!/usr/bin/env python3
"""Claude Code 桌面助手 — PyQt6 版本，跨平台兼容 (Windows/Mac/Linux)。"""
import sys
import os
import json
import uuid
import subprocess
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QComboBox, QInputDialog,
    QListWidget, QListWidgetItem, QScrollArea, QFrame,
    QDialog, QFileDialog, QMessageBox, QSizePolicy, QMenu,
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QObject, pyqtSlot, QPropertyAnimation, QEasingCurve, QRect, QPoint
from PyQt6.QtGui import QFont, QColor, QIcon
from PyQt6.QtWidgets import QGraphicsOpacityEffect

from claude_client import ClaudeClient

# ==================== 数据目录 ====================

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "conversations")
os.makedirs(DATA_DIR, exist_ok=True)

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
    thinking_ready = pyqtSignal(str, int)   # 思考完成（文本, 用时ms）
    error_occurred = pyqtSignal(str)

    def __init__(self, prompt, model, session_id=None):
        super().__init__()
        self.prompt = prompt
        self.model = model
        self.session_id = session_id  # 已有 session 则传入 --resume 续接

    @pyqtSlot()
    def run(self):
        try:
            cmd = [
                "claude", "-p", self.prompt,
                "--model", self.model,
                "--output-format", "stream-json",
                "--include-partial-messages",
                "--verbose",
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
                stderr=subprocess.PIPE,
            )

            # 用 TextIOWrapper 处理行缓冲
            import io
            import time
            stdout = io.TextIOWrapper(proc.stdout, encoding="utf-8", errors="replace", line_buffering=True)

            full_text = ""          # 累积正式回复文本
            thinking_text = ""      # 累积思考内容
            thinking_start_time = 0 # 思考开始时间戳
            thinking_emitted = False # 防止同一消息重复触发思考信号

            for line in stdout:
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
                        print(f"[SYSTEM] status={obj.get('status', '')}")
                    elif sub == "api_retry":
                        attempt = obj.get("attempt", 0)
                        max_retries = obj.get("max_retries", 0)
                        error = obj.get("error", "")
                        delay_ms = obj.get("retry_delay_ms", 0)
                        print(f"[SYSTEM] api_retry attempt={attempt}/{max_retries} error={error} delay={delay_ms:.0f}ms")

                # 流式事件
                elif msg_type == "stream_event":
                    event = obj.get("event", {})
                    event_type = event.get("type", "")

                    if event_type == "message_start":
                        msg_id = event.get("message", {}).get("id", "")
                        print(f"[EVENT] message_start id={msg_id[:16]}...")
                        thinking_emitted = False

                    elif event_type == "content_block_start":
                        block = event.get("content_block", {})
                        block_type = block.get("type", "")
                        print(f"[EVENT] content_block_start index={event.get('index', '')} type={block_type}")

                        if block_type == "thinking":
                            thinking_start_time = time.time()
                            thinking_text = ""
                            self.thinking_started.emit()

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
                            # 思考结束后，正式回复从头累积
                            full_text = ""

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
    """后台生成对话标题，不加入 session，单次请求。"""
    title_ready = pyqtSignal(str)  # 生成完成（可能为空字符串表示失败）

    def __init__(self, user_message, ai_reply):
        super().__init__()
        self.user_message = user_message
        self.ai_reply = ai_reply
        self._timeout = 30  # 超时阈值（秒）

    def run(self):
        try:
            # 构建极简 prompt
            prompt = (
                f"User said: {self.user_message[:200]}\n"
                f"AI replied (first 500 chars): {self.ai_reply[:500]}\n"
                f"Reply with ONLY a short Chinese title (max 12 chars) for this conversation. "
                f"No quotes, no explanation, just the title."
            )
            cmd = [
                "claude", "-p", prompt,
                "--model", "haiku",
                "--output-format", "stream-json",
            ]
            print(f"[TitleWorker] 启动，命令: {' '.join(cmd[:4])}...")
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            full_text = ""

            import io
            import time
            start = time.time()
            stdout = io.TextIOWrapper(proc.stdout, encoding="utf-8", errors="replace", line_buffering=True)

            for line in stdout:
                if time.time() - start > self._timeout:
                    print(f"[TitleWorker] 超时（{self._timeout}s），终止")
                    proc.kill()
                    return
                decoded = line.strip()
                if not decoded:
                    continue
                try:
                    obj = json.loads(decoded)
                    msg_type = obj.get("type", "")
                    if msg_type == "content_block_delta":
                        delta = obj.get("delta", {})
                        if delta.get("type") == "text_delta":
                            full_text += delta.get("text", "")
                except json.JSONDecodeError:
                    continue

            proc.wait(timeout=5)
            title = full_text.strip().strip('"').strip("'").strip()
            # 去掉 markdown 符号
            title = title.lstrip("#*`- ").strip()
            if title and len(title) <= 30:
                self.title_ready.emit(title)
        except Exception:
            pass  # 静默失败，调用方会降级为规则生成


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

        # 样式
        if role == "user":
            bubble.setStyleSheet("""
                #bubble { background-color: #DCF8C6; border-radius: 10px; }
                #bubble QLabel { color: #166534; background: transparent; }
            """)
            layout.addStretch()
            layout.addWidget(bubble)
        elif role == "system":
            bubble.setStyleSheet("""
                #bubble { background-color: #DBEAFE; border-radius: 10px; }
                #bubble QLabel { color: #1E40AF; background: transparent; }
            """)
            layout.addWidget(bubble)
            layout.addStretch()
        else:
            bubble.setStyleSheet("""
                #bubble { background-color: #F0F0F0; border-radius: 10px; }
                #bubble QLabel { color: #111; background: transparent; }
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
        self._content_label.setText(f"思考中{dots}")

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


class ThinkingBlock(QFrame):
    """可折叠的思考内容块。"""

    def __init__(self, text, duration_ms, parent=None):
        super().__init__(parent)
        self.setObjectName("thinkingBlock")
        self._expanded = False
        self._full_text = text

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
        icon_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #6B7280;")
        h_layout.addWidget(icon_label)

        title_label = QLabel(f"深度思考已完成")
        title_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #6B7280;")
        h_layout.addWidget(title_label)

        duration_label = QLabel(f"（用时 {self._format_duration(duration_ms)}）")
        duration_label.setStyleSheet("font-size: 12px; color: #9CA3AF;")
        h_layout.addWidget(duration_label)

        h_layout.addStretch()

        self._arrow_label = QLabel("▶")
        self._arrow_label.setStyleSheet("font-size: 10px; color: #9CA3AF;")
        h_layout.addWidget(self._arrow_label)

        layout.addWidget(header)

        # 内容区（默认折叠）
        self._content_frame = QFrame()
        self._content_frame.setObjectName("thinkingContent")
        c_layout = QVBoxLayout(self._content_frame)
        c_layout.setContentsMargins(10, 0, 10, 8)
        c_layout.setSpacing(0)

        self._content_label = QLabel(text)
        self._content_label.setWordWrap(True)
        self._content_label.setStyleSheet("font-size: 12px; color: #6B7280; line-height: 1.6;")
        self._content_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        c_layout.addWidget(self._content_label)

        self._content_frame.setVisible(False)
        layout.addWidget(self._content_frame)

        # 样式
        self.setStyleSheet("""
            #thinkingBlock { background-color: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 8px; margin: 2px 0; }
            #thinkingHeader { background-color: transparent; }
            #thinkingContent { background-color: transparent; }
        """)

        # 点击切换展开/折叠
        def toggle():
            self._expanded = not self._expanded
            self._content_frame.setVisible(self._expanded)
            self._arrow_label.setText("▼" if self._expanded else "▶")

        header.mousePressEvent = lambda e: toggle()

    @staticmethod
    def _format_duration(ms):
        """格式化时间为秒。"""
        if ms < 1000:
            return f"{ms}毫秒"
        return f"{ms / 1000:.0f}秒"


class ThinkingRow(QWidget):
    """思考行容器，包含一个 ThinkingBlock。"""

    def __init__(self, text, duration_ms, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(0)
        layout.addWidget(ThinkingBlock(text, duration_ms))
        layout.addStretch()


class LandingPage(QFrame):
    """空状态引导页，无对话时显示。"""

    send_clicked = pyqtSignal(str)  # 用户从着陆页发送消息

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("landingPage")
        self.setVisible(False)

        # 透明度效果
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._fade_animation = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        # 顶部友好提示
        hint_top = QLabel("你好，我是 Claude")
        hint_top.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_top.setStyleSheet("font-size: 26px; color: #1F2937; font-weight: bold; margin-bottom: 4px;")
        layout.addWidget(hint_top)

        hint_sub = QLabel("我可以帮你写代码、回答问题、分析文件")
        hint_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_sub.setStyleSheet("font-size: 15px; color: #6B7280;")
        layout.addWidget(hint_sub)

        layout.addSpacing(20)
        layout.addStretch()

        # 居中容器
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setSpacing(24)

        # 图标区域（简单几何图形，避免版权）
        icon_label = QLabel("✦")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setMinimumSize(80, 80)
        icon_label.setMaximumSize(80, 80)
        icon_label.setStyleSheet("""
            QLabel {
                background-color: #E0E7FF; border-radius: 40px;
                font-size: 36px; color: #4F46E5;
            }
        """)
        center_layout.addWidget(icon_label)

        # 文字提示
        hint_label = QLabel("请开始我们的对话吧")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_label.setStyleSheet("font-size: 16px; color: #9CA3AF;")
        center_layout.addWidget(hint_label)

        # 输入区
        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)

        self._input = QTextEdit()
        self._input.setPlaceholderText("输入消息...")
        self._input.setMinimumHeight(44)
        self._input.setMaximumHeight(100)
        self._input.setStyleSheet("""
            QTextEdit {
                border: 1px solid #D1D5DB; border-radius: 8px; padding: 8px 12px;
                font-size: 14px; background-color: white;
            }
            QTextEdit:focus { border-color: #3B82F6; }
        """)
        input_layout.addWidget(self._input)

        self._send_btn = QPushButton("发  送")
        self._send_btn.setStyleSheet("""
            QPushButton {
                background-color: #3B82F6; color: white; border: none;
                border-radius: 8px; padding: 8px 20px; font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { background-color: #2563EB; }
        """)
        self._send_btn.setMinimumHeight(44)
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
        self.setVisible(True)
        self._opacity_effect.setOpacity(0.01)
        self._fade_animation = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_animation.setDuration(duration)
        self._fade_animation.setStartValue(0.01)
        self._fade_animation.setEndValue(1.0)
        self._fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_animation.start()
        # 保持引用防止被 GC
        self._anim_ref = self._fade_animation

    def fade_out(self, duration=300, callback=None):
        """淡出动画。"""
        self._fade_animation = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_animation.setDuration(duration)
        self._fade_animation.setStartValue(1.0)
        self._fade_animation.setEndValue(0.01)
        self._fade_animation.setEasingCurve(QEasingCurve.Type.InCubic)
        if callback:
            self._fade_animation.finished.connect(callback)
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
        layout = QVBoxLayout(self)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; padding: 8px;")
        layout.addWidget(title_label)

        self.list_widget = QListWidget()
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
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self.new_btn = QPushButton("✚ 新建对话")
        self.new_btn.setStyleSheet("""
            QPushButton {
                background-color: #3B82F6; color: white; border: none;
                border-radius: 6px; padding: 10px; font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { background-color: #2563EB; }
        """)
        layout.addWidget(self.new_btn)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #ddd;")
        layout.addWidget(line)

        title = QLabel("历史对话")
        title.setStyleSheet("font-weight: bold; font-size: 14px; padding: 4px 0;")
        layout.addWidget(title)

        self.conv_list = QListWidget()
        self.conv_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ccc; border-radius: 6px; background-color: white;
            }
            QListWidget::item { padding: 8px; border-bottom: 1px solid #eee; }
            QListWidget::item:selected { background-color: #3B82F6; color: white; }
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 顶部：模型选择
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)
        top_bar.addWidget(QLabel("模型:"))

        self.model_combo = QComboBox()
        self.model_combo.addItems(["opus (最强)", "sonnet (推荐)", "haiku (最快)"])
        self.model_combo.setCurrentIndex(1)
        self.model_combo.setMinimumWidth(150)
        top_bar.addWidget(self.model_combo)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["普通模式", "Agent 模式 (多步骤任务)"])
        top_bar.addWidget(self.mode_combo)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        self._top_widgets = [top_bar.itemAt(i).widget() for i in range(top_bar.count()) if top_bar.itemAt(i).widget()]

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #ddd;")
        self._separator_line = line
        layout.addWidget(line)

        # 消息区
        self.msg_scroll = QScrollArea()
        self.msg_scroll.setWidgetResizable(True)
        self.msg_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.msg_scroll.setStyleSheet("QScrollArea { border: 1px solid #ccc; border-radius: 6px; background: white; }")

        self.msg_container = QWidget()
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
            ("@ 引用文件", "#3B82F6"), ("# 智能体", "#22C55E"),
            ("! 提示词", "#F97316"), ("$ Skills", "#A855F7"), (" 图片", "#0D9488"),
        ]
        for text, color in btn_defs:
            btn = QPushButton(text)
            key = text.strip().split()[0].replace("@", "ref").replace("#", "agent").replace("!", "prompt").replace("$", "skill").replace("图片", "image")
            btn.setStyleSheet(f"""
                QPushButton {{ background-color: {color}; color: white; border: none;
                    border-radius: 4px; padding: 4px 10px; font-size: 11px; }}
                QPushButton:hover {{ opacity: 0.85; }}
            """)
            setattr(self, f"btn_{key}", btn)
            toolbar.addWidget(btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._toolbar_widgets = [toolbar.itemAt(i).widget() for i in range(toolbar.count()) if toolbar.itemAt(i).widget()]

        # 输入区
        input_layout = QHBoxLayout()
        input_layout.setSpacing(6)

        self.input_box = QTextEdit()
        self.input_box.setPlaceholderText("输入消息...")
        self.input_box.setInputMethodHints(Qt.InputMethodHint.ImhNone)
        self.input_box.setStyleSheet("""
            QTextEdit {
                border: 1px solid #ccc; border-radius: 6px; padding: 8px 12px;
                font-size: 14px; background-color: white;
            }
            QTextEdit:focus { border-color: #3B82F6; }
        """)
        self.input_box.setMinimumHeight(36)
        self.input_box.setMaximumHeight(120)
        input_layout.addWidget(self.input_box)

        self.send_btn = QPushButton("发  送")
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #3B82F6; color: white; border: none;
                border-radius: 6px; padding: 8px 20px; font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { background-color: #2563EB; }
            QPushButton:disabled { background-color: #9CA3AF; }
        """)
        self.send_btn.setMinimumHeight(36)
        input_layout.addWidget(self.send_btn)
        layout.addLayout(input_layout)

        self._input_widgets = [input_layout.itemAt(i).widget() for i in range(input_layout.count()) if input_layout.itemAt(i).widget()]

        # 着陆页（无对话时显示，初始隐藏）
        self.landing_page = LandingPage()
        layout.addWidget(self.landing_page)

        # 默认显示着陆页
        self.show_landing()

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
        """给新添加的 widget 加淡入+上移动画。"""
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(0.01)
        widget.setGraphicsEffect(effect)
        # 淡入
        anim = QPropertyAnimation(effect, b"opacity")
        anim.setDuration(duration)
        anim.setStartValue(0.01)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        # 动画结束后清理 effect，避免长期占用
        anim.finished.connect(lambda: widget.setGraphicsEffect(None))
        # 保存引用
        widget._anim = anim

    def add_message(self, role, text):
        """添加消息到聊天区，带淡入动画。"""
        row = MessageRow(role, text)
        spring_index = self.msg_layout.count() - 1
        self.msg_layout.insertWidget(spring_index, row)
        self._animate_widget_in(row)
        self._scroll_to_bottom()
        return row

    def add_thinking_block(self, text, duration_ms):
        """添加思考块到聊天区（在 AI 回复前），带淡入动画。"""
        # 只检查紧邻最后一条消息之前的 widget（每轮对话各自一个思考块）
        last_idx = self.msg_layout.count() - 2  # 跳过弹簧
        if last_idx >= 0:
            item = self.msg_layout.itemAt(last_idx)
            if item and item.widget() and isinstance(item.widget(), ThinkingRow):
                return  # 紧邻的最后一条已经是 ThinkingRow，跳过
        row = ThinkingRow(text, duration_ms)
        spring_index = self.msg_layout.count() - 1
        self.msg_layout.insertWidget(spring_index, row)
        self._animate_widget_in(row)
        self._scroll_to_bottom()
        return row

    def _scroll_to_bottom(self):
        QTimer.singleShot(50, lambda: self.msg_scroll.verticalScrollBar().setValue(
            self.msg_scroll.verticalScrollBar().maximum()
        ))

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


class RightPanel(QFrame):
    """右侧面板：项目文件树 + 文件变更。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(280)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        title = QLabel("项目文件")
        title.setStyleSheet("font-weight: bold; font-size: 14px; padding: 4px 0;")
        layout.addWidget(title)

        self.file_list = QListWidget()
        self.file_list.setStyleSheet("""
            QListWidget { border: 1px solid #ccc; border-radius: 6px; background-color: white; }
            QListWidget::item { padding: 4px 8px; }
        """)
        layout.addWidget(self.file_list)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #ddd;")
        layout.addWidget(line)

        change_title = QLabel("文件变更")
        change_title.setStyleSheet("font-weight: bold; font-size: 14px; padding: 4px 0;")
        layout.addWidget(change_title)

        self.change_list = QListWidget()
        self.change_list.setStyleSheet("""
            QListWidget { border: 1px solid #ccc; border-radius: 6px; background-color: white; }
            QListWidget::item { padding: 4px 8px; }
        """)
        self.change_list.addItem("暂无变更")
        layout.addWidget(self.change_list)


# ==================== 主窗口 ====================

class MainWindow(QMainWindow):
    """主窗口。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Claude Code 桌面助手")
        self.resize(1400, 800)
        self.setMinimumSize(900, 500)

        self.claude_client = ClaudeClient()
        self.current_conv_id = None
        self._building_response = False
        self._pending_session_id = None
        self._is_first_send = False
        self._session_last_active = None  # session 最后活跃时间
        self._SESSION_TIMEOUT = 1800  # session 超时阈值（秒），30 分钟

        self._build()
        QTimer.singleShot(300, self._init_content)

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
        self.center_panel.send_btn.clicked.connect(self._on_send)
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
        self.center_panel.clear_messages()
        self.center_panel.hide_landing()

        for msg in conv.get("messages", []):
            role = msg.get("role", "user")
            text = msg.get("content", "")
            if role == "system":
                continue
            self.center_panel.add_message(role, text)

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

        # 更新按钮
        self.center_panel.send_btn.setEnabled(False)
        self.center_panel.send_btn.setText("思考中...")
        self._building_response = True

        # 添加 AI 占位消息
        self.center_panel.add_message("assistant", "思考中...")

        # 获取当前对话的 session_id（用于续接历史对话）
        session_id = conv.get("session_id") if conv else None
        self._pending_session_id = None  # 重置 pending

        # 构建对话上下文（只取最后一条用户消息，历史由 Claude session 管理）
        prompt = self.claude_client.build_prompt(messages)
        model_name = self.center_panel.model_combo.currentText()
        model = {"opus (最强)": "opus", "sonnet (推荐)": "sonnet", "haiku (最快)": "haiku"}.get(model_name, "sonnet")

        # 创建 Claude 工作线程
        self._claude_thread = QThread()
        self._claude_worker = ClaudeWorker(prompt, model, session_id=session_id)
        self._claude_worker.moveToThread(self._claude_thread)
        self._claude_worker.chunk_ready.connect(self._on_chunk)
        self._claude_worker.result_ready.connect(self._on_claude_result)
        self._claude_worker.session_ready.connect(self._on_session_ready)
        self._claude_worker.thinking_started.connect(self._on_thinking_started)
        self._claude_worker.thinking_ready.connect(self._on_thinking_ready)
        self._claude_worker.error_occurred.connect(self._on_claude_error)
        self._claude_thread.started.connect(self._claude_worker.run)
        self._claude_thread.start()

    def _on_session_ready(self, session_id):
        """收到 Claude 的 session_id（新对话首次创建）。"""
        self._pending_session_id = session_id

    def _on_thinking_started(self):
        """Claude 开始思考（替换占位消息）。"""
        # 将"思考中..."占位消息替换为思考块占位
        pass  # 思考内容会在 thinking_ready 中完整回传

    def _on_thinking_ready(self, text, duration_ms):
        """收到完整的思考内容，插入思考块。"""
        self.center_panel.add_thinking_block(text, duration_ms)

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

    def _on_chunk(self, text):
        """收到 AI 的流式回复片段（主线程）。"""
        self.center_panel.update_last_message(text)

    def _on_done(self, full_text):
        """AI 回复完成（子线程）。"""
        self._building_response = False
        self._finish_response(full_text)

    def _finish_response(self, full_text):
        """在主线程完成回复处理。"""
        self.center_panel.update_last_message(full_text)
        self._session_last_active = datetime.now()  # 更新活跃时间

        if self.current_conv_id:
            conv = load_conversation(self.current_conv_id)
            if conv:
                messages = conv.get("messages", [])
                messages.append({"role": "assistant", "content": full_text})
                session_id = self._pending_session_id or conv.get("session_id")

                if self._is_first_send:
                    # 首次发送：先保存规则生成的临时标题，再后台调用 AI 生成
                    temp_title = self._generate_title(full_text)
                    save_conversation(self.current_conv_id, temp_title, messages, session_id)
                    self._is_first_send = False
                    self._refresh_sidebar_preview()
                    # 后台 AI 生成标题（不阻塞 UI）
                    self._start_ai_title_generation(full_text)
                else:
                    save_conversation(self.current_conv_id, conv.get("title", "新增对话"), messages, session_id)

                self._pending_session_id = None

        self.center_panel.send_btn.setEnabled(True)
        self.center_panel.send_btn.setText("发  送")

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
            if conv and conv.get("title", "新增对话") == "新增对话":
                # 只在标题还是默认值时才替换
                save_conversation(self.current_conv_id, title, conv.get("messages", []), conv.get("session_id"))
                self._refresh_sidebar_preview()
                print(f"[Title] AI 生成标题: {title}")

    def _on_title_worker_done(self):
        """TitleWorker 线程完成——无论成功失败都到此。"""
        print(f"[Title] TitleWorker 线程完成")

    def _handle_error(self, error_msg):
        self.center_panel.update_last_message(f"[出错] {error_msg}")
        self.center_panel.send_btn.setEnabled(True)
        self.center_panel.send_btn.setText("发  送")

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

        conv_id = str(uuid.uuid4())[:8]
        title = "新增对话"
        save_conversation(conv_id, title, [], session_id=None)
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
        if popup.exec_() and popup.selected:
            self.center_panel.input_box.insertPlainText(f" #{popup.selected} ")

    def _insert_bang(self):
        items = [(n, t) for n, t in PROMPT_TEMPLATES.items()]
        popup = PopupList("插入提示词模板", items, self)
        if popup.exec_() and popup.selected:
            self.center_panel.input_box.setText(popup.selected)

    def _insert_dollar(self):
        popup = PopupList("调用 Skills", SKILLS_LIST, self)
        if popup.exec_() and popup.selected:
            self.center_panel.input_box.insertPlainText(f" /{popup.selected} ")

    def _upload_image(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择图片", "", "图片文件 (*.png *.jpg *.jpeg *.gif *.webp);;所有文件 (*.*)"
        )
        if filepath:
            self.center_panel.add_message("user", f"[已上传图片: {os.path.basename(filepath)}]")

    def closeEvent(self, event):
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
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
