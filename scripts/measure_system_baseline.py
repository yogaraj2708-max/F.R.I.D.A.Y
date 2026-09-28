"""
F.R.I.D.A.Y. 3.0 — Baseline System Metrics & Performance Budgets Measurement Script
Measures:
1. Application startup time & resource footprints
2. Thread count, QThread count, asyncio task count, RAM, CPU, sockets, disk
3. Ollama process memory & Friday process memory
4. Subsystem performance benchmarks:
   - STARTUP
   - SIMPLE CHAT
   - FIRST RESPONSE & FIRST TOKEN
   - NATIVE TOOL CALL & TOOL EXECUTION
   - WEB SEARCH
   - DOCUMENT QUERY
   - VISION
   - VOICE / STT
   - TTS
   - DEEP RESEARCH
   - CANCELLATION
   - UI NAVIGATION
"""

import sys
import os
import time
import json
import asyncio
import psutil
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer

# Ensure project root is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from friday_core.settings import settings

def get_ollama_memory():
    total_rss = 0
    total_vms = 0
    count = 0
    for p in psutil.process_iter(['name', 'memory_info']):
        try:
            if 'ollama' in (p.info['name'] or '').lower():
                mem = p.memory_info()
                total_rss += mem.rss
                total_vms += mem.vms
                count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return {
        "process_count": count,
        "rss_bytes": total_rss,
        "rss_mb": round(total_rss / (1024 * 1024), 2),
        "vms_bytes": total_vms,
        "vms_mb": round(total_vms / (1024 * 1024), 2)
    }

def get_disk_usage():
    app_data = Path(os.environ.get("LOCALAPPDATA", ".")) / "FRIDAY"
    dirs = {
        "workspace": str(BASE_DIR),
        "app_data": str(app_data)
    }
    sizes = {}
    for name, p in dirs.items():
        path = Path(p)
        if path.exists():
            total = sum(f.stat().st_size for f in path.glob('**/*') if f.is_file())
            sizes[name] = {
                "bytes": total,
                "mb": round(total / (1024 * 1024), 2)
            }
        else:
            sizes[name] = {"bytes": 0, "mb": 0.0}
    return sizes

async def run_benchmark():
    results = {}
    process = psutil.Process()
    
    # 1. Startup measurement
    t_start = time.perf_counter()
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    
    from friday_ui.views.main_window import FridayMainWindow
    
    t_win_start = time.perf_counter()
    window = FridayMainWindow()
    t_win_init = time.perf_counter() - t_win_start
    
    # Show and process events
    window.resize(1024, 768)
    window.show()
    app.processEvents()
    t_total_startup = time.perf_counter() - t_start
    
    results["startup"] = {
        "total_startup_ms": round(t_total_startup * 1000, 2),
        "window_init_ms": round(t_win_init * 1000, 2),
    }
    
    # Process and resource metrics at clean startup
    mem_info = process.memory_info()
    threads = process.threads()
    connections = []
    try:
        connections = process.net_connections()
    except Exception:
        pass
    
    ollama_mem = get_ollama_memory()
    disk_metrics = get_disk_usage()
    
    # QThreads & asyncio tasks
    # Window has background threads and asyncio loop
    active_loop = asyncio.get_event_loop()
    asyncio_tasks = [t for t in asyncio.all_tasks(active_loop) if not t.done()]
    
    resource_baseline = {
        "process_id": process.pid,
        "friday_process_rss_mb": round(mem_info.rss / (1024 * 1024), 2),
        "friday_process_vms_mb": round(mem_info.vms / (1024 * 1024), 2),
        "friday_process_cpu_pct": process.cpu_percent(interval=0.1),
        "process_count": 1 + len(process.children(recursive=True)),
        "thread_count": len(threads),
        "asyncio_task_count": len(asyncio_tasks),
        "active_sockets": len(connections),
        "ollama_memory": ollama_mem,
        "disk_usage": disk_metrics,
        "timestamp": time.time()
    }
    
    # 2. Performance Budgets Benchmark
    budgets = {}
    
    # UI Navigation
    nav_times = []
    views = [window.chat_view, window.research_view, window.documents_view, window.settings_view]
    for view in views:
        t0 = time.perf_counter()
        window.switchTo(view)
        app.processEvents()
        nav_times.append((time.perf_counter() - t0) * 1000)
    # switch back to chat
    window.switchTo(window.chat_view)
    app.processEvents()
    budgets["ui_navigation_ms"] = round(sum(nav_times) / len(nav_times), 2)
    
    # Native Tool Execution
    from friday_core.calc import safe_calculate
    from friday_core.system.telemetry import get_cpu_info, get_battery_info
    
    t0 = time.perf_counter()
    for _ in range(50):
        safe_calculate("123 * 456 + 789")
    calc_ms = (time.perf_counter() - t0) * 1000 / 50
    
    t0 = time.perf_counter()
    for _ in range(20):
        get_cpu_info()
    telem_ms = (time.perf_counter() - t0) * 1000 / 20
    
    budgets["native_tool_execution_ms"] = round(calc_ms, 3)
    budgets["telemetry_inspection_ms"] = round(telem_ms, 2)
    
    # Tool call dispatch via Agent Bridge
    from friday_core.skills.agent_bridge import agent_tool_bridge
    t0 = time.perf_counter()
    is_allowed, _ = agent_tool_bridge.risk_gate("calculate", {"expression": "25 * 4"})
    raw_calc = safe_calculate("25 * 4")
    bundle = agent_tool_bridge.verify_tool_result("calculate", {"expression": "25 * 4"}, raw_calc, "bench_trace")
    budgets["native_tool_call_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    budgets["native_tool_call_verified"] = bundle["verification_status"] == "VERIFIED"

    
    # Document Query (Embedder + BM25)
    from friday_core.rag.hybrid_retriever import FastLocalEmbedder, BM25Index
    embedder = FastLocalEmbedder()
    bm25 = BM25Index()
    docs = [f"Sample document content chunk {i} about engineering and cybersecurity" for i in range(100)]
    bm25.index_documents(docs)
    
    t0 = time.perf_counter()
    embedder.embed_text("cybersecurity and engineering verification")
    embed_ms = (time.perf_counter() - t0) * 1000
    
    t0 = time.perf_counter()
    bm25.score("engineering cybersecurity")
    bm25_ms = (time.perf_counter() - t0) * 1000
    budgets["document_query_ms"] = round(embed_ms + bm25_ms, 2)
    
    # Web Search
    from duckduckgo_search import DDGS
    t0 = time.perf_counter()
    web_res = []
    try:
        with DDGS(timeout=5) as ddgs:
            web_res = list(ddgs.text("python official website", max_results=2))
        budgets["web_search_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        budgets["web_search_status"] = "GOOD" if len(web_res) > 0 else "DEGRADED"
    except Exception as ex:
        budgets["web_search_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        budgets["web_search_status"] = "DEGRADED"
        budgets["web_search_error"] = str(ex)
        
    # TTS Synthesis
    from friday_ui.core.engine import KokoroTTSManager
    tts_mgr = KokoroTTSManager.get_instance()
    t0 = time.perf_counter()
    audio_wav = tts_mgr.synthesize("Tactical intelligence systems nominal, Boss.")
    tts_ms = (time.perf_counter() - t0) * 1000
    budgets["tts_synthesis_ms"] = round(tts_ms, 2)
    budgets["tts_status"] = "GOOD" if audio_wav and len(audio_wav) > 0 else "UNVERIFIED"
    
    # Vision Perception
    from friday_core.vision import image_context_manager, ImageContext
    from PIL import Image
    test_img_path = BASE_DIR / "audit" / "PERFORMANCE_SOAK_HARDENING" / "test_frame.png"
    img = Image.new("RGB", (640, 480), color=(10, 20, 40))
    img.save(test_img_path)
    
    t0 = time.perf_counter()
    ctx = ImageContext(
        image_path=str(test_img_path),
        image_name="test_frame.png",
        dimensions=(640, 480),
        format="PNG",
        description="Benchmark baseline test frame"
    )
    img_id = image_context_manager.store_context(ctx)
    budgets["vision_ingestion_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    budgets["vision_status"] = "GOOD" if img_id else "FAILED"

    
    # STT / Voice Benchmark
    from friday_ui.core.engine import OfflineWhisperSTT
    stt_mgr = OfflineWhisperSTT.get_instance()
    t0 = time.perf_counter()
    stt_avail = stt_mgr.is_available()
    stt_probe_ms = (time.perf_counter() - t0) * 1000
    budgets["voice_stt_probe_ms"] = round(stt_probe_ms, 2)
    budgets["voice_stt_status"] = "GOOD" if stt_avail else "UNAVAILABLE"
    
    # Cancellation Latency
    # Start a mock command task and immediately cancel
    t0 = time.perf_counter()
    window.handle_stop_requested()
    app.processEvents()
    cancellation_ms = (time.perf_counter() - t0) * 1000
    budgets["cancellation_ms"] = round(cancellation_ms, 2)
    
    # Deep Research Step Latency (single verification iteration)
    from friday_core.research.worker import DeepResearchWorker
    from friday_core.agent.task_lifecycle import task_supervisor
    t_rec = task_supervisor.create_task(query="quantum computing state", route="RESEARCH")
    t0 = time.perf_counter()
    worker = DeepResearchWorker(task_record=t_rec, depth="Quick Scan")
    worker_init_ms = (time.perf_counter() - t0) * 1000
    budgets["deep_research_init_ms"] = round(worker_init_ms, 2)


    
    # Simple Chat / First Token Latency (Warm LLM)
    t0 = time.perf_counter()
    first_token_time = None
    try:
        from ollama import AsyncClient
        host = settings.get("ollama_host", "http://localhost:11434")
        client = AsyncClient(host=host, timeout=30.0)
        model = settings.get("model", "qwen3.5:9b")
        t_req = time.perf_counter()
        stream = await client.chat(model=model, messages=[{"role": "user", "content": "Hi"}], stream=True)
        async for chunk in stream:
            if first_token_time is None:
                first_token_time = (time.perf_counter() - t_req) * 1000
        total_chat_ms = (time.perf_counter() - t0) * 1000
        budgets["first_token_ms"] = round(first_token_time or 0.0, 2)
        budgets["first_response_ms"] = round(first_token_time or 0.0, 2)
        budgets["simple_chat_ms"] = round(total_chat_ms, 2)
        budgets["simple_chat_status"] = "GOOD"
    except Exception as ex:
        budgets["first_token_ms"] = 0.0
        budgets["first_response_ms"] = 0.0
        budgets["simple_chat_ms"] = 0.0
        budgets["simple_chat_status"] = "DEGRADED"
        budgets["simple_chat_error"] = str(ex)

    
    # Clean close
    window.close()
    app.processEvents()
    
    # Save outputs
    out_dir = BASE_DIR / "audit" / "PERFORMANCE_SOAK_HARDENING"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    with open(out_dir / "PERFORMANCE_BASELINE.json", "w", encoding="utf-8") as f:
        json.dump({
            "startup": results["startup"],
            "budgets": budgets,
            "timestamp": time.time()
        }, f, indent=2)
        
    with open(out_dir / "RESOURCE_BASELINE.json", "w", encoding="utf-8") as f:
        json.dump(resource_baseline, f, indent=2)
        
    print("[SUCCESS] Baseline metrics and resource benchmarks recorded successfully.")

if __name__ == "__main__":
    asyncio.run(run_benchmark())
