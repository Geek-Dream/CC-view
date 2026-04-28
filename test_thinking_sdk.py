#!/usr/bin/env python3
"""测试 SDK thinking 输出是否包含文本。"""
import sys
sys.path.insert(0, "/Users/wl/开发/My File/CC-view")

import anyio
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from claude_agent_sdk.types import AssistantMessage, StreamEvent, ThinkingBlock, TextBlock


async def test_thinking():
    options = ClaudeAgentOptions(
        model="opus",
        cwd="/Users/wl/开发/My File/CC-view",
        thinking={"type": "adaptive", "display": "summarized"},
    )

    client = ClaudeSDKClient(options=options)
    try:
        await client.connect(lambda: (_ for _ in ()).athrow(StopAsyncIteration))

        # 发送测试消息（触发思考）
        await client.query("请简要分析一下 Python 中装饰器的工作原理，用中文回答")

        async for msg in client.receive_response():
            msg_type = type(msg).__name__
            if isinstance(msg, StreamEvent):
                event_type = msg.event.get("type", "")
                print(f"  StreamEvent: {event_type}")
                if event_type == "content_block_start":
                    block = msg.event.get("content_block", {})
                    print(f"    block_type: {block.get('type', '')}")
            elif isinstance(msg, AssistantMessage):
                print(f"\n  AssistantMessage, content blocks: {len(msg.content)}")
                for i, block in enumerate(msg.content):
                    block_type = type(block).__name__
                    print(f"    Block {i}: {block_type}")
                    if isinstance(block, ThinkingBlock):
                        thinking_len = len(block.thinking or "")
                        print(f"      thinking length: {thinking_len}")
                        if thinking_len > 0:
                            print(f"      thinking preview: {repr(block.thinking[:200])}")
                        else:
                            print(f"      WARNING: thinking is EMPTY!")
                            print(f"      signature: {repr(block.signature[:50]) if block.signature else 'None'}")
                    elif isinstance(block, TextBlock):
                        print(f"      text preview: {repr(block.text[:100])}")
            else:
                print(f"  {msg_type}")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    anyio.run(test_thinking)
