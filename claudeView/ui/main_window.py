"""主窗口模块 — 三栏布局的容器。"""
import customtkinter as ctk
from ui.sidebar import SidebarPanel
from ui.chat_panel import ChatPanel
from ui.file_panel import FilePanel


class MainWindow(ctk.CTk):
    """主窗口：左侧对话历史 + 中间聊天区 + 右侧文件面板。"""

    def __init__(self):
        super().__init__()
        self.title("Claude Code 桌面助手")
        self.geometry("1400x800")
        self.minsize(1000, 600)

        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        self._callbacks = {
            "on_send": None,
            "on_new_conversation": None,
            "on_select_conversation": None,
            "on_model_change": None,
            "on_file_click": None,
        }

        self._build_layout()

    def _build_layout(self):
        # 使用 PanedWindow 实现可调整宽度的三栏
        self.paned = ctk.CTkFrame(self)
        self.paned.pack(fill="both", expand=True, padx=5, pady=5)

        # 左侧栏
        self.sidebar = SidebarPanel(
            self.paned, width=250,
            on_new_conversation=self._cb("on_new_conversation"),
            on_select_conversation=self._cb("on_select_conversation"),
        )
        self.sidebar.pack(side="left", fill="both", padx=(0, 2))

        # 中间聊天区
        self.chat_panel = ChatPanel(
            self.paned,
            on_send=self._cb("on_send"),
            on_model_change=self._cb("on_model_change"),
        )
        self.chat_panel.pack(side="left", fill="both", expand=True, padx=2)

        # 右侧文件面板
        self.file_panel = FilePanel(
            self.paned, width=300,
            on_file_click=self._cb("on_file_click"),
        )
        self.file_panel.pack(side="left", fill="both", padx=(2, 0))

    def _cb(self, name):
        def wrapper(*args, **kwargs):
            func = self._callbacks.get(name)
            if func:
                return func(*args, **kwargs)
        return wrapper

    # ===== 对外 API =====

    def set_on_send(self, func):
        self._callbacks["on_send"] = func

    def set_on_new_conversation(self, func):
        self._callbacks["on_new_conversation"] = func

    def set_on_select_conversation(self, func):
        self._callbacks["on_select_conversation"] = func

    def set_on_model_change(self, func):
        self._callbacks["on_model_change"] = func

    def set_on_file_click(self, func):
        self._callbacks["on_file_click"] = func

    def refresh_sidebar(self, conversations):
        self.sidebar.refresh_conversations(conversations)

    def add_chat_message(self, role, text):
        if role == "assistant":
            self.chat_panel.add_assistant_message(text)
        else:
            self.chat_panel._add_message(role, text)

    def update_file_tree(self, tree_data):
        self.file_panel.update_file_tree(tree_data)

    def update_file_changes(self, modified, added, deleted):
        self.file_panel.update_changes(modified, added, deleted)
