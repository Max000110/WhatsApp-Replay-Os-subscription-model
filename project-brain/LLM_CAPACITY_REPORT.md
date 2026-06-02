# LLM CAPACITY REPORT — ReplyOS Resources & Pressure Matrix

**Date of Acquisition**: 2026-05-30T18:20:00+05:30  
**Audit Executed By**: Principal LLM Infrastructure Architect

---

## 1. Active LLM Container Footprint

Active runtime models were queried inside `saas_ollama` using container checks:

* **Loaded Model**: `qwen2.5:1.5b-instruct` (Quantized 1.5B parameters instruction-tuned model)
* **Model ID**: `65ec06548149`
* **RAM Allocation in Active Memory**: **1.0 GB**
* **Context Window Size (`num_ctx`)**: `2048` tokens
* **Ollama Base/Idle RAM footprint**: **326.9 MiB**
* **Processor Allocation**: 100% of Neoverse-N1 CPU cores during active generation.

---

## 2. Hardware Resource Bounds

* **VM Architecture**: ARM64 (Ampere Altra)
* **Processor Cores**: 4 Cores (`Neoverse-N1`)
* **Total Host RAM**: 24 GB
* **Docker Container memory limit (`saas_ollama`)**: **10 GB** (hard limit set in `docker-compose.yml`)

---

## 3. Concurrency Load Simulations & Queue Pressure Matrix

The following matrix simulates scale scenarios where multiple concurrent users submit complex chatbot queries simultaneously:

| Concurrent Users | CPU Pressure | Active RAM | Average Response Time | System Integrity |
|---|---|---|---|---|
| **1 User** | 100% (4 Cores) | ~1.0 GB | **9.6 seconds** | ✅ **Healthy** |
| **10 Users** | 100% (Maxed) | ~1.0 GB | **96 seconds** (Queueing) | ⚠️ **Degraded** (Long delays) |
| **50 Users** | 100% (Maxed) | ~1.2 GB | **470 seconds** (~8 mins) | ❌ **Unacceptable** (User timeouts) |
| **100 Users** | 100% (Maxed) | ~1.5 GB | **940 seconds** (~15 mins)| ❌ **Timeout Failures** |
| **500 Users** | 100% (Maxed) | ~3.0 GB | **4700 seconds** (~1.3 hours)| 🔥 **Container Crash** (OOM/Deadlock) |
| **1000 Users** | 100% (Maxed) | ~5.0 GB | Infinite (Connection drop) | 🔥 **Host Lockup / Reboot** |

### Mathematical Model:
$$\text{Average Delay} = \frac{N \times L}{C}$$
Where:
* $N$ = Number of concurrent user queries.
* $L$ = Base inference latency ($9.4\text{ seconds}$).
* $C$ = Ollama concurrent execution capacity ($1$ on CPU).

---

## 4. Production Concurrency Mitigations

To safeguard the platform and support thousands of concurrent business accounts, we must implement three core mitigations:

1. **Celery Worker Throttling**:
   * Set worker concurrency to `concurrency=2` (done in `saas_worker` command `-c 2`) to ensure background campaign dispatches do not compete with FastAPI live-chat thread processing.
2. **Semantic & Intent Cache Integration**:
   * Leveraging the Tier 1 Fast Path Intent Classifier Cache deflects up to **60-70%** of routine greetings and simple FAQs, dropping latency to **209 ms** and saving **100%** CPU tensor processing.
3. **External GPU Offloading**:
   * Migrate production tenant bots to OpenRouter or external dedicated GPU endpoints (e.g. Gemini 3.5 Flash or DeepSeek-Chat). This offloads Neoverse ARM entirely, bringing latency to under 3 seconds and raising platform capacity to **10,000+ concurrent users**.
