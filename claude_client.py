"""Claude CLI 客户端模块 — 简单可靠的 claude 命令封装。"""
import subprocess


MODEL_MAP = {
    "opus (最强)": "opus",
    "sonnet (推荐)": "sonnet",
    "haiku (最快)": "haiku",
}


class ClaudeClient:
    """简单的 claude CLI 调用。"""

    def __init__(self):
        self._proc = None

    def build_prompt(self, messages):
        """将消息列表拼接为纯文本。"""
        if not messages:
            return ""
        lines = []
        for msg in messages:
            role = msg.get("role", "")
            text = msg.get("content", "")
            if role == "user":
                lines.append(text)
        return lines[-1] if lines else ""

    def send_message(self, prompt, model_alias="sonnet (推荐)", on_chunk=None, on_done=None, on_error=None):
        """发送消息到 claude CLI。"""
        model_name = MODEL_MAP.get(model_alias, "sonnet")

        try:
            cmd = [
                "claude", "--print",
                "--model", model_name,
                prompt,
            ]
            print(f"[ClaudeClient] 执行: {' '.join(cmd)}")

            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # 读取输出
            out, err = self._proc.communicate()
            result = out.decode('utf-8', errors='replace').strip()

            print(f"[ClaudeClient] 结果: {result[:50]}...")

            # 发送结果
            if on_chunk:
                on_chunk(result)
            if on_done:
                on_done(result)

        except Exception as e:
            print(f"[ClaudeClient] 错误: {e}")
            if on_error:
                on_error(str(e))
        finally:
            self._proc = None

    def stop(self):
        """停止当前对话。"""
        if self._proc:
            try:
                self._proc.terminate()
            except:
                pass
