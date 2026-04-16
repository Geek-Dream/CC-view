#!/usr/bin/env python3
"""Claude Code 桌面助手 — PyQt5 版本，跨平台兼容 (Windows/Mac/Linux)。"""
import sys
import os
import json
import uuid
import subprocess
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QComboBox,
    QListWidget, QListWidgetItem, QScrollArea, QFrame,
    QDialog, QFileDialog, QMessageBox, QSizePolicy,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, pyqtSlot
from PyQt5.QtGui import QFont, QColor

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

def save_conversation(conv_id, title, messages):
    filepath = os.path.join(DATA_DIR, f"{conv_id}.json")
    data = {
        "id": conv_id,
        "title": title,
        "created_at": datetime.now().isoformat(),
        "messages": messages,
    }
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


# ==================== 消息气泡 ====================

class MessageRow(QWidget):
    """消息气泡，QLabel 支持文字选择复制。"""

    def __init__(self, role, text, parent=None):
        super().__init__(parent)
        self.role = role

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(0)

        bubble = QFrame()
        bubble.setObjectName("bubble")
        bubble.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)

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
        # 让文字可以选择和复制
        content.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
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

    def update_text(self, text):
        """更新消息文字（用于流式输出）。"""
        if hasattr(self, '_content_label'):
            self._content_label.setText(text)


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
            item.setData(Qt.UserRole, name)
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget)
        self.list_widget.itemDoubleClicked.connect(self._on_select)

    def _on_select(self, item):
        self.selected = item.data(Qt.UserRole)
        self.accept()


# ==================== 面板 ====================

class LeftPanel(QFrame):
    """左侧面板：新建对话 + 历史对话列表。"""

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
        line.setFrameShape(QFrame.HLine)
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
        layout.addWidget(self.conv_list)

    def clear_conversations(self):
        self.conv_list.clear()

    def add_conversation(self, title_text, preview, conv_id):
        label = title_text + (f"  {preview[:30]}" if preview else "")
        item = QListWidgetItem(label)
        item.setData(Qt.UserRole, conv_id)
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

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #ddd;")
        layout.addWidget(line)

        # 消息区
        self.msg_scroll = QScrollArea()
        self.msg_scroll.setWidgetResizable(True)
        self.msg_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
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

        # 输入区
        input_layout = QHBoxLayout()
        input_layout.setSpacing(6)

        self.input_box = QTextEdit()
        self.input_box.setPlaceholderText("输入消息...")
        self.input_box.setInputMethodHints(Qt.ImhNone)
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

    def clear_messages(self):
        """清空消息区，显示欢迎消息。"""
        while self.msg_layout.count() > 1:
            item = self.msg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.add_message("system", "欢迎使用 Claude Code 桌面助手！\n\n你可以直接输入问题，或使用快捷功能：\n  @ 引用文件    # 调用智能体    ! 插入提示词    $ 调用 Skills")

    def add_message(self, role, text):
        """添加消息到聊天区。"""
        row = MessageRow(role, text)
        spring_index = self.msg_layout.count() - 1
        self.msg_layout.insertWidget(spring_index, row)
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
        line.setFrameShape(QFrame.HLine)
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
        self._pending_text = ""

        self._build()
        QTimer.singleShot(300, self._init_content)

        # 后台 git 工作线程
        from PyQt5.QtCore import QThread
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
        self.center_panel.btn_ref.clicked.connect(self._insert_at)
        self.center_panel.btn_agent.clicked.connect(self._insert_hash)
        self.center_panel.btn_prompt.clicked.connect(self._insert_bang)
        self.center_panel.btn_skill.clicked.connect(self._insert_dollar)
        self.center_panel.btn_image.clicked.connect(self._upload_image)

    def _init_content(self):
        self._load_saved_conversations()
        self._schedule_git_files()
        self._schedule_git_status()

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
        self.center_panel.clear_messages()

        for msg in conv.get("messages", []):
            role = msg.get("role", "user")
            text = msg.get("content", "")
            if role == "system":
                continue
            self.center_panel.add_message(role, text)

        # 高亮左侧列表项
        for i in range(self.left_panel.conv_list.count()):
            item = self.left_panel.conv_list.item(i)
            if item.data(Qt.UserRole) == conv_id:
                self.left_panel.conv_list.setCurrentItem(item)
                break

    def _on_select_conversation(self, item):
        conv_id = item.data(Qt.UserRole)
        if conv_id:
            self._select_conversation(conv_id)

    def _schedule_git_files(self):
        from PyQt5.QtCore import QMetaObject, Qt as QtType
        QMetaObject.invokeMethod(self.git_worker, "fetch_files", QtType.QueuedConnection)

    def _schedule_git_status(self):
        from PyQt5.QtCore import QMetaObject, Qt as QtType
        QMetaObject.invokeMethod(self.git_worker, "fetch_status", QtType.QueuedConnection)

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
        if event.key() == Qt.Key_Return and not (event.modifiers() & Qt.ShiftModifier):
            self._on_send()
            return
        QTextEdit.keyPressEvent(self.center_panel.input_box, event)

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

        conv_id = self.current_conv_id
        conv = load_conversation(conv_id)
        if not conv:
            return
        messages = conv.get("messages", [])

        # 添加并显示用户消息
        messages.append({"role": "user", "content": text})
        self.center_panel.add_message("user", text)

        # 保存用户消息
        save_conversation(conv_id, conv.get("title", "新对话"), messages)
        self._refresh_sidebar_preview()

        # 更新按钮
        self.center_panel.send_btn.setEnabled(False)
        self.center_panel.send_btn.setText("思考中...")
        self._building_response = True
        self._pending_text = ""

        # 添加 AI 占位消息
        self.center_panel.add_message("assistant", "思考中...")

        # 构建对话上下文
        prompt = self.claude_client.build_prompt(messages)
        model = self.center_panel.model_combo.currentText()

        self.claude_client.send_message(
            prompt,
            model_alias=model,
            on_chunk=self._on_chunk,
            on_done=self._on_done,
            on_error=self._on_error,
        )

    def _on_chunk(self, text):
        """收到 AI 的一段回复（子线程）。"""
        self._pending_text += text
        self.center_panel.update_last_message(self._pending_text)

    def _on_done(self, full_text):
        """AI 回复完成（子线程）。"""
        self._building_response = False
        self._finish_response(full_text)

    def _finish_response(self, full_text):
        """在主线程完成回复处理。"""
        self.center_panel.update_last_message(full_text)

        # 保存 AI 回复
        conv = load_conversation(self.current_conv_id)
        if conv:
            messages = conv.get("messages", [])
            messages.append({"role": "assistant", "content": full_text})
            save_conversation(self.current_conv_id, conv.get("title", "新对话"), messages)
            self._refresh_sidebar_preview()

        self.center_panel.send_btn.setEnabled(True)
        self.center_panel.send_btn.setText("发  送")

    def _on_error(self, error_msg):
        print(f"[DEBUG] _on_error called: {error_msg}")
        self._handle_error(error_msg)

    def _handle_error(self, error_msg):
        print(f"[DEBUG] _handle_error: {error_msg}")
        self._building_response = False
        self.center_panel.update_last_message(f"[出错] {error_msg}")
        self.center_panel.send_btn.setEnabled(True)
        self.center_panel.send_btn.setText("发  送")

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
                if item.data(Qt.UserRole) == self.current_conv_id:
                    self.left_panel.conv_list.setCurrentItem(item)
                    break

    def _new_conversation(self, silent=False):
        if self._building_response:
            QMessageBox.warning(self, "提示", "请等待当前对话完成")
            return

        conv_id = str(uuid.uuid4())[:8]
        title = f"对话 {conv_id}"
        save_conversation(conv_id, title, [])
        self.current_conv_id = conv_id
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
        self.claude_client.stop()
        self._worker_thread.quit()
        self._worker_thread.wait(2000)
        super().closeEvent(event)


def main():
    # 修复 Mac 上 PyQt5 中文输入法候选词不显示的问题
    os.environ["QT_IM_MODULE"] = "xim"

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
