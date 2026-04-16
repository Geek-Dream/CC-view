"""文件变更监控模块 — 通过 git 状态跟踪文件的修改/新增/删除。"""
import os
import subprocess
import threading
import time


class FileWatcher:
    """监控 git 仓库中的文件变更。"""

    def __init__(self, work_dir=None, on_change=None):
        self.work_dir = work_dir or os.getcwd()
        self.on_change = on_change  # callback(modified, added, deleted)
        self._running = False
        self._thread = None

    def get_git_status(self):
        """获取 git 状态，返回 (modified, added, deleted) 列表。"""
        modified = []
        added = []
        deleted = []

        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.work_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return modified, added, deleted

            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                # git status --porcelain 格式: XY path
                status = line[:2].strip()
                path = line[3:]

                if status in ("M", "MM", "AM"):
                    modified.append(path)
                elif status in ("A", "AM", "??"):
                    added.append(path)
                elif status == "D":
                    deleted.append(path)

        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return modified, added, deleted

    def get_file_tree(self, max_depth=3):
        """获取项目文件树结构（仅 git 跟踪的文件）。"""
        tree = {"name": os.path.basename(self.work_dir), "type": "directory", "children": []}

        try:
            result = subprocess.run(
                ["git", "ls-files"],
                cwd=self.work_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return tree

            files = result.stdout.strip().split("\n")
            self._build_tree(tree, files, max_depth)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return tree

    def _build_tree(self, node, files, max_depth, current_depth=0):
        """将文件列表构建树结构。"""
        if current_depth >= max_depth:
            return

        dirs = {}
        for f in files:
            parts = f.split("/", 1)
            if len(parts) == 1:
                node["children"].append({"name": parts[0], "type": "file", "path": f})
            else:
                dir_name = parts[0]
                if dir_name not in dirs:
                    dirs[dir_name] = {"name": dir_name, "type": "directory", "children": []}
                    node["children"].append(dirs[dir_name])
                # 递归添加剩余路径
                remaining = parts[1]
                self._add_to_dir(dirs[dir_name], remaining, f, current_depth + 1, max_depth)

    def _add_to_dir(self, node, remaining_path, full_path, current_depth, max_depth):
        """添加文件到指定目录节点。"""
        parts = remaining_path.split("/", 1)
        if len(parts) == 1:
            node["children"].append({"name": parts[0], "type": "file", "path": full_path})
        else:
            dir_name = parts[0]
            child = None
            for c in node["children"]:
                if c["name"] == dir_name:
                    child = c
                    break
            if child is None:
                child = {"name": dir_name, "type": "directory", "children": []}
                node["children"].append(child)
            if current_depth + 1 < max_depth:
                self._add_to_dir(child, parts[1], full_path, current_depth + 1, max_depth)

    def get_file_diff(self, filepath):
        """获取单个文件的 diff。"""
        try:
            result = subprocess.run(
                ["git", "diff", "HEAD", "--", filepath],
                cwd=self.work_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return ""

    def start(self, interval=5):
        """启动定时监控。"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll, args=(interval,), daemon=True)
        self._thread.start()

    def _poll(self, interval):
        """定时轮询 git 状态。"""
        while self._running:
            modified, added, deleted = self.get_git_status()
            if self.on_change:
                self.on_change(modified, added, deleted)
            time.sleep(interval)

    def stop(self):
        """停止监控。"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
