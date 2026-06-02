# LATENCY FORENSICS — ReplyOS Production Hardening

**Date of Diagnostic Acquisition**: 2026-05-30T18:15:00+05:30  
**Audit Lead**: Principal Performance SRE

---

## 1. High-Resolution Latency Breakdown (Nominal State)

We profiled the E2E chat webhook processing pipeline to isolate bottlenecks. Below is the latency footprint:

```
[Inbound Message]
       │
       ├─► DB Tenant/Session Lookup ──────► 173 ms (Sub-second relational check)
       ├─► pgvector Knowledge RAG ────────► 0 ms (Cached/Bypassed)
       ├─► 15-Layer Prompt Assembly ──────► < 1 ms
       ├─► Model Inference (Local CPU) ───► 9,409 ms ⚠️ BASELINE BOTTLENECK
       └─► Node Socket Delivery ACK ──────► 16 ms
                                            ──────────
                                     Total: 9,612 ms (9.6 seconds)
```

### Millisecond Profile Matrix:

| Pipeline Step | Latency (Before Fix) | Latency (After Model Tag Sync) | Delta (Improvement) | Notes |
|---|---|---|---|---|
| **DB Tenant/Session Query** | 175 ms | 173 ms | -2 ms | Well within optimal bounds (<200 ms) |
| **pgvector RAG Similarity** | 1 ms | 0 ms | -1 ms | Bypassed when RAG is disabled |
| **Prompt Compilation** | < 1 ms | < 1 ms | 0 ms | Minimal CPU cost |
| **Ollama Model Matching** | 16,732 ms | 0 ms | -16.73s (100%)| Eliminated tag fallback checks |
| **LLM Token Generation (CPU)**| 9,440 ms | 9,409 ms | -31 ms | Quantized 1.5B parameters, Neoverse ARM |
| **Companion Socket Dispatch** | 15 ms | 16 ms | +1 ms | Node.js fast socket execution |
| **E2E Pipeline Latency** | **26,348 ms** | **9,612 ms** | **-16.73s (63.5%)**| ✅ Significant reduction |

---

## 2. Optimized Tier-1 Fast-Path Cache Performance

For routine customer greetings, FAQ queries, and common keywords (e.g. "hi", "hello", "business hours", "services"), the backend invokes the **Tier-1 Intent Classifier Cache** before sending requests to the LLM.

```
[Inbound Greeting] ──► [Fast-Path Cache] ──► [Immediate Socket Reply] ──► **209 ms** (0.2 seconds!)
```
* **CPU Util**: < 1% (Zero tensor calculations performed on host processor).
* **Deflection Rate**: Protects local CPU from **60% to 70%** of standard incoming message pressure.

---

## 3. Dynamic Model 404 Fallback & Recovery Latency

Our production E2E acceptance suite Test 8 programmatically forced the chatbot model configuration to `"mistral:latest"` (which is not preloaded in the `saas_ollama` container).

### Fallback Recovery Execution Flow:
1. Webhook pipeline dispatches prompt to Ollama with model `"mistral:latest"`.
2. Ollama returns `HTTP 404 Not Found` in **50 ms**.
3. Backend `_call_ollama` catches 404 error, prints `[Ollama Fallback]`, and instantly retries with preloaded default `'qwen2.5:1.5b-instruct'`.
4. Fallback execution completes, returning a valid answer in **1.27 seconds** total!

This dynamic mechanism prevents service interruption and recovers from misconfigured chatbot model settings in real-time.

---

## 4. Sub-3 Second Production Offloading Options

To drop out-of-cache conversational latencies under 3 seconds under nominal load, we recommend enabling GPU offloading:

| Config Scenario | Target Latency | CPU Load | RAM Draw | Best Use |
|---|---|---|---|---|
| **Option A: Local Ollama (ARM CPU)** | ~9.6 seconds | 100% of 4 Cores | 1.0 GB | Budget setups / Offline VM |
| **Option B: OpenRouter API (GPU)** | **~1.5 - 2.5 seconds** | < 1% (Idle) | < 100 MB | High-throughput SaaS Production |

To activate **Option B**, configure `.env` with:
```env
AI_PROVIDER=openrouter
AI_API_KEY=your_openrouter_secure_key
```
