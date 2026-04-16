"""右侧文件面板模块 — 项目文件树 + 文件变更记录。"""
import customtkinter as ctk


class FilePanel(ctk.CTkFrame):
    """右侧栏：项目文件树 + 文件变更。"""

    def __init__(self, master, on_file_click=None, **kwargs):
        super().__init__(master, **kwargs)
        self.on_file_click = on_file_click
        self._build_ui()

    def _build_ui(self):
        # ===== 上半部分：项目文件树 =====
        ctk.CTkLabel(
            self, text=" 项目文件", font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=10, pady=(10, 5))

        self.tree_scroll = ctk.CTkScrollableFrame(self)
        self.tree_scroll.pack(fill="both", expand=True, padx=5, pady=5)

        # ===== 分隔线 =====
        ctk.CTkFrame(self, height=2, fg_color=("gray70", "gray30")).pack(fill="x", padx=10, pady=5)

        # ===== 下半部分：文件变更记录 =====
        ctk.CTkLabel(
            self, text=" 文件变更", font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=10, pady=(5, 5))

        self.change_scroll = ctk.CTkScrollableFrame(self)
        self.change_scroll.pack(fill="both", expand=True, padx=5, pady=5)

    def update_file_tree(self, tree_data):
        """更新文件树显示。"""
        for widget in self.tree_scroll.winfo_children():
            widget.destroy()
        self._render_tree(tree_data, self.tree_scroll, level=0)

    def _render_tree(self, node, parent, level=0):
        """递归渲染文件树，使用 pack 布局。"""
        indent = "  " * level
        if node["type"] == "file":
            ctk.CTkButton(
                parent, text=f"{indent} {node['name']}",
                font=ctk.CTkFont(size=12), anchor="w", height=25,
                command=lambda p=node.get("path", ""): self._on_file_click(p),
            ).pack(fill="x", padx=(level * 15, 0))
        else:
            ctk.CTkLabel(
                parent, text=f"{indent} {node['name']}/",
                font=ctk.CTkFont(size=12, weight="bold"), anchor="w",
            ).pack(fill="x", padx=(level * 15, 0))

            for child in node.get("children", []):
                self._render_tree(child, parent, level + 1)

    def update_changes(self, modified, added, deleted):
        """更新文件变更记录。"""
        for widget in self.change_scroll.winfo_children():
            widget.destroy()

        color_map = {"modified": "#F97316", "added": "#22C55E", "deleted": "#EF4444"}
        label_map = {"modified": "已修改", "added": "已新增", "deleted": "已删除"}

        has_changes = False
        for status, files in [("modified", modified), ("added", added), ("deleted", deleted)]:
            for f in files:
                has_changes = True
                ctk.CTkLabel(
                    self.change_scroll, text=f"[{label_map[status]}] {f}",
                    font=ctk.CTkFont(size=12), text_color=color_map[status],
                    anchor="w",
                ).pack(fill="x", padx=5, pady=1)

        if not has_changes:
            ctk.CTkLabel(
                self.change_scroll, text="暂无变更",
                font=ctk.CTkFont(size=12), text_color="gray",
            ).pack(padx=5, pady=5)

    def _on_file_click(self, filepath):
        if self.on_file_click:
            self.on_file_click(filepath)
