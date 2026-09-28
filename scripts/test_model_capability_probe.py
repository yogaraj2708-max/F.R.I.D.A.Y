import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import asyncio
import ollama
from friday_core.settings import settings

async def test_capability(model_name):
    client = ollama.AsyncClient()
    probe_tool = {
        'type': 'function',
        'function': {
            'name': 'probe_tool',
            'description': 'A diagnostic probe tool.',
            'parameters': {
                'type': 'object',
                'properties': {'arg': {'type': 'string'}},
                'required': ['arg']
            }
        }
    }
    msgs = [{'role': 'user', 'content': 'Please call the tool probe_tool with argument arg equal to test_123.'}]
    try:
        resp = await client.chat(model=model_name, messages=msgs, tools=[probe_tool], stream=False)
        msg = resp.message if hasattr(resp, 'message') else resp.get('message', {})
        t_calls = getattr(msg, 'tool_calls', None) if hasattr(msg, 'tool_calls') else msg.get('tool_calls')
        content = getattr(msg, 'content', '') if hasattr(msg, 'content') else msg.get('content', '')
        print(f"[{model_name}] native tool_calls: {t_calls}")
        if not t_calls:
            print(f"[{model_name}] emitted text content: {content[:120]}")
        return bool(t_calls)
    except Exception as e:
        print(f"[{model_name}] exception: {e}")
        return False

async def main():
    configured_model = settings.get("model", "deepseek-r1:8b")
    print(f"Configured main model: {configured_model}")
    candidates = [configured_model, "llama3.2:1b", "qwen3.5:9b"]
    seen = set()
    for m in candidates:
        if m in seen:
            continue
        seen.add(m)
        has_tool_calling = await test_capability(m)
        print(f"==> {m} native tool capability: {'SUPPORTED' if has_tool_calling else 'UNAVAILABLE'}\n")

if __name__ == "__main__":
    asyncio.run(main())
