"""Claude CLI 客户端模块 — 支持流式输出的 claude 命令封装。"""
import subprocess
import threading
import json


MODEL_MAP = {
    "opus (最强)": "opus",
    "sonnet (推荐)": "sonnet",
    "haiku (最快)": "haiku",
}


class ClaudeClient:
    """支持流式输出的 claude CLI 调用。"""

    def __init__(self):
        self._proc = None
        self._running = False

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
        """发送消息到 claude CLI，支持流式输出。"""
        model_name = MODEL_MAP.get(model_alias, "sonnet")
        self._running = True

        def _run():
            try:
                cmd = [
                    "claude", "--print",
                    "--model", model_name,
                    "--output-format", "stream-json",
                    "--verbose",
                    prompt,
                ]
                print(f"[ClaudeClient] 执行: {' '.join(cmd)}")

                self._proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

                full_text = ""
                thinking_sent = False

                # 使用 readline 逐行读取
                while self._running:
                    line = self._proc.stdout.readline()
                    if not line:
                        break
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                        dtype = data.get("type", "")

                        if dtype == "assistant":
                            msg = data.get("message", {})
                            content = msg.get("content", [])

                            for block in content:
                                block_type = block.get("type", "")

                                if block_type == "thinking":
                                    thinking = block.get("thinking", "")
                                    if thinking and on_chunk and not thinking_sent:
                                        on_chunk(f"[ 🤔 正在思考... ]\n\n{thinking}\n\n")
                                        thinking_sent = True

                                elif block_type == "text":
                                    text = block.get("text", "")
                                    if text and on_chunk:
                                        # 每次都发送完整的文本内容用于流式显示
                                        on_chunk(text)

                        elif dtype == "result":
                            result = data.get("result", "")
                            if result and not full_text:
                                full_text = result
                            duration = data.get("duration_ms", 0)
                            cost = data.get("total_cost_usd", 0)
                            usage = data.get("usage", {})
                            output_tokens = usage.get("output_tokens", 0)
                            if on_chunk:
                                info = f"\n\n[耗时: {duration/1000:.1f}s | tokens: {output_tokens} | 费用: ${cost:.4f}]"
                                on_chunk(info)
                            break

                    except json.JSONDecodeError:
                        continue

                if self._proc.poll() is None:
                    self._proc.wait()

                if on_done:
                    on_done(full_text)

            except Exception as e:
                print(f"[ClaudeClient] 错误: {e}")
                if on_error:
                    on_error(str(e))
            finally:
                self._running = False
                self._proc = None

        threading.Thread(target=_run, daemon=True).start()

    def stop(self):
        """停止当前对话。"""
        self._running = False
        if self._proc:
            try:
                self._proc.terminate()
            except:
                pass
