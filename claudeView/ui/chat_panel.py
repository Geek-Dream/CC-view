"""中间聊天面板模块 — 消息显示 + 输入框 + 快捷功能。"""
import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import os


# 内置提示词模板
PROMPT_TEMPLATES = {
    "代码审查": "请审查以下代码，指出潜在问题和改进建议：",
    "写单元测试": "请为以下代码编写完整的单元测试：",
    "解释代码": "请详细解释以下代码的工作原理：",
    "性能优化": "请分析以下代码的性能瓶颈并提供优化方案：",
    "生成文档": "请为以下代码生成清晰的中文注释和文档：",
}

# 可用智能体列表
AGENT_LIST = [
    {"name": "general-purpose", "desc": "通用智能体，处理复杂多步任务"},
    {"name": "Explore", "desc": "快速探索代码库，搜索和查找"},
    {"name": "Plan", "desc": "软件架构师，设计实现方案"},
]

# 可用 Skills 列表
SKILLS_LIST = [
    {"name": "commit", "desc": "创建 git 提交"},
    {"name": "review-pr", "desc": "审查拉取请求"},
    {"name": "simplify", "desc": "审查代码质量并优化"},
    {"name": "security-review", "desc": "安全审查"},
]


class ChatPanel(ctk.CTkFrame):
    """中间区域：对话消息 + 输入区。"""

    def __init__(self, master, on_send=None, on_model_change=None, **kwargs):
        super().__init__(master, **kwargs)
        self.on_send = on_send
        self.on_model_change = on_model_change
        self.images = []
        self._msg_count = 0
        self._build_ui()

    def _build_ui(self):
        # ===== 顶部：模型选择器 + 模式切换 =====
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(top_bar, text="模型:", font=ctk.CTkFont(size=13)).pack(side="left", padx=(0, 5))
        self.model_var = ctk.StringVar(value="sonnet (推荐)")
        ctk.CTkOptionMenu(
            top_bar, variable=self.model_var,
            values=["opus (最强)", "sonnet (推荐)", "haiku (最快)"],
            command=self._on_model_change, width=150,
        ).pack(side="left", padx=(0, 15))

        self.mode_var = ctk.StringVar(value="普通模式")
        ctk.CTkOptionMenu(
            top_bar, variable=self.mode_var,
            values=["普通模式", "Agent 模式 (多步骤任务)"],
            width=180,
        ).pack(side="left")

        # ===== 中间：消息显示区域 (用 CTkFrame + 内嵌 CTkScrollableFrame) =====
        self.msg_frame = ctk.CTkFrame(self)
        self.msg_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.msg_scroll = ctk.CTkScrollableFrame(self.msg_frame)
        self.msg_scroll.pack(fill="both", expand=True, padx=2, pady=2)

        # 添加欢迎消息
        self._add_message("system", "欢迎使用 Claude Code 桌面助手！\n\n你可以直接输入问题，或使用快捷功能：\n  @ 引用文件    # 调用智能体    ! 插入提示词    $ 调用 Skills")

        # ===== 底部：输入区 =====
        input_frame = ctk.CTkFrame(self, fg_color="transparent")
        input_frame.pack(fill="x", padx=10, pady=5)

        # 快捷功能按钮行
        toolbar = ctk.CTkFrame(input_frame, fg_color="transparent")
        toolbar.pack(fill="x", pady=(0, 5))

        btn_kw = {"width": 80, "height": 30, "font": ctk.CTkFont(size=11)}
        ctk.CTkButton(toolbar, text="@ 引用", fg_color="#3B82F6", text_color="white", command=self._insert_at, **btn_kw).pack(side="left", padx=2)
        ctk.CTkButton(toolbar, text="# 智能体", fg_color="#22C55E", text_color="white", command=self._insert_hash, **btn_kw).pack(side="left", padx=2)
        ctk.CTkButton(toolbar, text="! 提示词", fg_color="#F97316", text_color="white", command=self._insert_bang, **btn_kw).pack(side="left", padx=2)
        ctk.CTkButton(toolbar, text="$ Skills", fg_color="#A855F7", text_color="white", command=self._insert_dollar, **btn_kw).pack(side="left", padx=2)
        ctk.CTkButton(toolbar, text=" 图片", fg_color="#0D9488", text_color="white", command=self._upload_image, **btn_kw).pack(side="left", padx=2)

        # 输入框
        self.text_input = ctk.CTkTextbox(input_frame, height=80, font=ctk.CTkFont(size=14), wrap="word")
        self.text_input.pack(fill="x", pady=(0, 5))
        self.text_input.bind("<Key>", self._on_key)

        # 发送按钮
        ctk.CTkButton(
            input_frame, text="发 送", font=ctk.CTkFont(size=14, weight="bold"),
            command=self._on_send, height=40,
        ).pack(side="right")

    def _on_key(self, event):
        if event.keycode == 13 and not (event.state & 0x1):  # Enter (无 Shift)
            self._on_send()
            return "break"

    def _on_send(self):
        text = self.text_input.get("1.0", "end").strip()
        if not text:
            return
        self._add_message("user", text)
        self.text_input.delete("1.0", "end")
        if self.on_send:
            self.on_send(text)

    def _on_model_change(self, value):
        if self.on_model_change:
            self.on_model_change(value)

    def _add_message(self, role, text):
        """用 pack 添加消息，避免 CTkScrollableFrame 的 grid 问题。"""
        color_map = {
            "user": ("#DCF8C6", "#2E5B3C"),
            "assistant": ("#F0F0F0", "#333333"),
            "system": ("#E3F2FD", "#1565C0"),
        }
        align_map = {"user": "e", "assistant": "w", "system": "w"}

        row_frame = ctk.CTkFrame(self.msg_scroll, fg_color="transparent")
        row_frame.pack(fill="x", pady=2, padx=2)

        bubble = ctk.CTkFrame(
            row_frame, fg_color=color_map.get(role, ("gray90", "gray20")),
            corner_radius=10,
        )

        if align_map.get(role) == "e":
            bubble.pack(side="right")
        else:
            bubble.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            bubble, text=text, font=ctk.CTkFont(size=13),
            anchor="w", justify="left", wraplength=550,
        ).pack(padx=10, pady=8)

        self._msg_count += 1
        # 自动滚动到底部
        self.msg_scroll._parent_canvas.yview_moveto(1.0)

    def add_assistant_message(self, text):
        self._add_message("assistant", text)

    def _insert_at(self):
        filepath = filedialog.askopenfilename(title="选择要引用的文件")
        if filepath:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read(2000)
                self.text_input.insert("end", f"\n[引用文件: {os.path.basename(filepath)}]\n```\n{content}\n```\n")
            except Exception as e:
                messagebox.showerror("错误", f"无法读取文件: {e}")

    def _insert_hash(self):
        popup = ctk.CTkToplevel(self)
        popup.title("选择智能体")
        popup.geometry("350x200")
        popup.grab_set()
        ctk.CTkLabel(popup, text="选择要调用的智能体:", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=10)
        for agent in AGENT_LIST:
            ctk.CTkButton(
                popup, text=f"{agent['name']} — {agent['desc']}",
                command=lambda a=agent["name"]: (self.text_input.insert("end", f"\n#{a}\n"), popup.destroy()),
            ).pack(pady=3, padx=20, fill="x")

    def _insert_bang(self):
        popup = ctk.CTkToplevel(self)
        popup.title("插入提示词模板")
        popup.geometry("350x250")
        popup.grab_set()
        ctk.CTkLabel(popup, text="选择提示词模板:", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=10)
        for name, template in PROMPT_TEMPLATES.items():
            ctk.CTkButton(
                popup, text=name,
                command=lambda t=template: (self.text_input.insert("end", t), popup.destroy()),
            ).pack(pady=3, padx=20, fill="x")

    def _insert_dollar(self):
        popup = ctk.CTkToplevel(self)
        popup.title("调用 Skills")
        popup.geometry("350x200")
        popup.grab_set()
        ctk.CTkLabel(popup, text="选择要调用的 Skill:", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=10)
        for skill in SKILLS_LIST:
            ctk.CTkButton(
                popup, text=f"{skill['name']} — {skill['desc']}",
                command=lambda s=skill["name"]: (self.text_input.insert("end", f"\n/{s}\n"), popup.destroy()),
            ).pack(pady=3, padx=20, fill="x")

    def _upload_image(self):
        filepath = filedialog.askopenfilename(
            title="选择图片",
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.gif *.webp"), ("所有文件", "*.*")],
        )
        if filepath:
            try:
                img = Image.open(filepath)
                img.thumbnail((200, 200))
                photo = ImageTk.PhotoImage(img)
                self.images.append(photo)

                row_frame = ctk.CTkFrame(self.msg_scroll, fg_color="transparent")
                row_frame.pack(fill="x", pady=2, padx=2)

                bubble = ctk.CTkFrame(row_frame, fg_color=("gray90", "gray20"), corner_radius=10)
                bubble.pack(side="right")

                ctk.CTkLabel(bubble, image=photo, text="").pack(padx=5, pady=5)
                ctk.CTkLabel(bubble, text=f"[已上传图片: {os.path.basename(filepath)}]", font=ctk.CTkFont(size=10)).pack()

                self.msg_scroll._parent_canvas.yview_moveto(1.0)
            except Exception as e:
                messagebox.showerror("错误", f"无法加载图片: {e}")
