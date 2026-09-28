# Forensic Analysis: Elimination of Hidden 1B Preflight Router

## Root Cause of False-Positive Web Searches
In previous iterations, `_detect_tool_model()` resolved a secondary small model (such as `llama3.2:1b`) to run preflight tool selection ahead of the user-configured main reasoning model.
When the user entered prompts such as `"this is your brain"`, the smaller preflight model hallucinated a web search intent for `"this is your brain"`, executing unnecessary network queries and polluting context.

## Architectural Elimination
1. **Deleted `_detect_tool_model`**: Removed `self.tool_model` and `_detect_tool_model` entirely from `FridayBrain`.
2. **Dynamic Capability Probe**: Implemented `get_model_tool_capability_status(target_model)` using the standard `test_echo` schema directly on the configured main model.
3. **Sole Authority**: If the main model is verified (`llama3.2:1b`, `qwen3.5:9b`, etc.), it directly receives tools and decides tool invocation.
4. **Honest Reporting**: If the main model lacks native tool calling (e.g. `deepseek-r1:8b`), the agent loop records `NATIVE_TOOL_CALLING = UNSUPPORTED_FOR_SELECTED_MODEL` without falling back to a hidden small model or keyword interception.
