"""Claude Code 进程管理模块 — 负责启动子进程、发送消息、接收流式输出。"""
import os
import json
import threading
import subprocess
import queue
import tempfile
from datetime import datetime


class ClaudeProcess:
    """管理单个 Claude Code 子进程的生命周期。"""

    def __init__(self, conversation_id, work_dir=None, on_output=None):
        self.conversation_id = conversation_id
        self.work_dir = work_dir or os.getcwd()
        self.on_output = on_output  # callback(output_text)
        self.process = None
        self.output_queue = queue.Queue()
        self.running = False
        self.input_pipe = None
        self.output_pipe = None

    def start(self):
        """启动 Claude Code 子进程（使用 pty 实现伪终端）。"""
        if self.running:
            return

        self.running = True

        # 使用 pty 获取类终端的交互
        import pty
        master_fd, slave_fd = pty.openpty()

        env = os.environ.copy()
        env["CLAUDE_CODE_DISABLE_NONESSENTIAL_ENV"] = "true"

        self.process = subprocess.Popen(
            ["claude"],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=self.work_dir,
            env=env,
            preexec_fn=os.setsid,
        )

        os.close(slave_fd)
        self.input_pipe = master_fd

        # 启动读取线程
        self._read_thread = threading.Thread(target=self._read_output, args=(master_fd,), daemon=True)
        self._read_thread.start()

    def _read_output(self, fd):
        """从 pty 主端读取输出。"""
        buffer = b""
        while self.running:
            try:
                data = os.read(fd, 4096)
                if not data:
                    break
                buffer += data
                # 按行分割并回调
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    text = line.decode("utf-8", errors="replace")
                    if self.on_output:
                        self.on_output(text)
            except OSError:
                break

    def send_message(self, message):
        """向 Claude Code 进程发送消息。"""
        if not self.running or self.input_pipe is None:
            return
        try:
            data = (message + "\n").encode("utf-8")
            os.write(self.input_pipe, data)
        except OSError:
            pass

    def stop(self):
        """停止进程。"""
        self.running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=3)
            except Exception:
                self.process.kill()
        if self.input_pipe is not None:
            try:
                os.close(self.input_pipe)
            except OSError:
                pass
