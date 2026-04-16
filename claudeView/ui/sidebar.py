"""左侧栏模块 — 历史对话列表 + 新建对话按钮。"""
import customtkinter as ctk
from datetime import datetime


class SidebarPanel(ctk.CTkFrame):
    """左侧栏：对话历史 + 新建对话。"""

    def __init__(self, master, on_new_conversation=None, on_select_conversation=None, **kwargs):
        super().__init__(master, **kwargs)
        self.on_new = on_new_conversation
        self.on_select = on_select_conversation
        self._btn_map = {}
        self._build_ui()

    def _build_ui(self):
        # 新建对话按钮
        ctk.CTkButton(
            self, text="✚ 新建对话", font=ctk.CTkFont(size=14),
            command=self._on_new, height=40,
        ).pack(fill="x", padx=10, pady=10)

        # 分隔线
        ctk.CTkFrame(self, height=2, fg_color=("gray70", "gray30")).pack(fill="x", padx=10, pady=5)

        # 标题
        ctk.CTkLabel(
            self, text="历史对话", font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=10, pady=(5, 0))

        # 对话列表容器（可滚动）
        self.list_scroll = ctk.CTkScrollableFrame(self)
        self.list_scroll.pack(fill="both", expand=True, padx=5, pady=5)

    def _on_new(self):
        if self.on_new:
            self.on_new()

    def select_conversation(self, conv_id):
        for btn in self._btn_map.values():
            btn.configure(fg_color=("gray85", "gray25"))
        if conv_id in self._btn_map:
            self._btn_map[conv_id].configure(fg_color=("gray70", "gray40"))

    def refresh_conversations(self, conversations):
        """刷新对话列表。"""
        for widget in self.list_scroll.winfo_children():
            widget.destroy()
        self._btn_map = {}

        for conv in conversations:
            btn = ctk.CTkButton(
                self.list_scroll,
                text=f"{conv['title']}\n{conv.get('preview', '')[:40]}",
                font=ctk.CTkFont(size=12),
                anchor="w",
                height=50,
                command=lambda cid=conv["id"]: self._on_select(cid),
            )
            btn.pack(fill="x", padx=5, pady=2)
            self._btn_map[conv["id"]] = btn

    def _on_select(self, conv_id):
        self.select_conversation(conv_id)
        if self.on_select:
            self.on_select(conv_id)
