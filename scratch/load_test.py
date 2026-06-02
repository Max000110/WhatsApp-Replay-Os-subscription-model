import asyncio
import httpx
import time
import sys

BASE_URL = "http://localhost:8000/api/v1"
BOT_ID = "7f6e1078-de20-4265-8d9a-22c7f26e9d5f"
CONV_ID = "5eeaf42e-df8d-479e-ae83-d268381f6ff9"

async def get_auth_headers():
    cust_login_payload = {
        "email": "diagtest2@example.com",
        "password": "TestPass123!"
    }
    async with httpx.AsyncClient() as client:
        res = await client.post(f"{BASE_URL}/auth/login", json=cust_login_payload)
        if res.status_code != 200:
            print("Failed to authenticate test user:", res.text)
            sys.exit(1)
        token = res.json().get("access_token")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

async def get_system_health(headers):
    # Log in as admin to get system health
    admin_login_payload = {
        "email": "admin@replyos.com",
        "password": "AdminAccess2026!"
    }
    async with httpx.AsyncClient() as client:
        res = await client.post(f"{BASE_URL}/admin/auth/login", json=admin_login_payload)
        admin_token = res.json().get("access_token")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        
        health_res = await client.get(f"{BASE_URL}/admin/system-health", headers=admin_headers)
        return health_res.json()

async def send_sandbox_query(client, headers, question, query_type):
    payload = {
        "test_question": question,
        "conversation_id": CONV_ID
    }
    start = time.time()
    try:
        res = await client.post(
            f"{BASE_URL}/bots/{BOT_ID}/test-prompt", 
            json=payload, 
            headers=headers,
            timeout=120.0
        )
        latency = (time.time() - start) * 1000.0
        if res.status_code == 200:
            return {"type": query_type, "success": True, "latency": latency, "error": None}
        else:
            return {"type": query_type, "success": False, "latency": latency, "error": f"HTTP {res.status_code}: {res.text}"}
    except Exception as e:
        latency = (time.time() - start) * 1000.0
        return {"type": query_type, "success": False, "latency": latency, "error": str(e)}

async def main():
    print("======================================================================")
    print("                100 CONCURRENT REQUEST LOAD TEST SIMULATOR            ")
    print("======================================================================\n")
    
    headers = await get_auth_headers()
    print("Authenticated successfully.")
    
    # Measure starting resources
    initial_health = await get_system_health(headers)
    print(f"Starting System State -> CPU: {initial_health['system']['cpu_percent']}%, RAM: {initial_health['system']['ram_percent']}%")
    
    # 50 Fast Path queries (Greetings, FAQ, hours, contact, location)
    fast_path_questions = [
        "hi", "hello", "hey", "hola",
        "working hours", "hours of operation", "what are your hours?",
        "where are you located?", "what is your location?", "address",
        "pricing catalog", "prices?", "what is the price?",
        "what services do you provide?", "services rooms AC / non AC",
        "wifi details?", "contact information", "email", "phone number"
    ]
    
    # 50 LLM reasoning queries (not matching fast path keywords)
    llm_questions = [
        "Explain general relativity in 3 sentences.",
        "How do plants perform photosynthesis?",
        "Write a 4-line poem about rain.",
        "What is the capital of France?",
        "Summarize the story of Romeo and Juliet.",
        "Why is the sky blue during the day?",
        "What are the benefits of sleep?",
        "Describe the process of deep learning.",
        "What are the differences between SQL and NoSQL?",
        "Help me plan a 3-day itinerary in Paris."
    ]
    
    # Construct 100 tasks (50 fast path, 50 LLM)
    tasks = []
    # 50 Fast Path
    for i in range(50):
        question = fast_path_questions[i % len(fast_path_questions)]
        tasks.append((question, "fast-path"))
    # 50 LLM
    for i in range(50):
        question = llm_questions[i % len(llm_questions)]
        tasks.append((question, "llm-inference"))
        
    print(f"Prepared 100 concurrent tasks (50 Fast-Path, 50 LLM). Triggering simulation...")
    
    start_test_time = time.time()
    async with httpx.AsyncClient() as client:
        futures = [send_sandbox_query(client, headers, q, t) for q, t in tasks]
        results = await asyncio.gather(*futures)
    total_test_duration = time.time() - start_test_time
    
    # Measure ending resources
    final_health = await get_system_health(headers)
    
    print("\n======================================================================")
    print("                          BENCHMARK METRICS                           ")
    print("======================================================================")
    
    success_count = sum(1 for r in results if r["success"])
    fail_count = sum(1 for r in results if not r["success"])
    
    fast_path_results = [r for r in results if r["type"] == "fast-path"]
    llm_results = [r for r in results if r["type"] == "llm-inference"]
    
    fp_successes = [r for r in fast_path_results if r["success"]]
    llm_successes = [r for r in llm_results if r["success"]]
    
    # Latencies
    fp_latencies = [r["latency"] for r in fp_successes]
    llm_latencies = [r["latency"] for r in llm_successes]
    
    avg_fp = sum(fp_latencies) / len(fp_latencies) if fp_latencies else 0.0
    min_fp = min(fp_latencies) if fp_latencies else 0.0
    max_fp = max(fp_latencies) if fp_latencies else 0.0
    
    avg_llm = sum(llm_latencies) / len(llm_latencies) if llm_latencies else 0.0
    min_llm = min(llm_latencies) if llm_latencies else 0.0
    max_llm = max(llm_latencies) if llm_latencies else 0.0
    
    print(f"Total Completed In: {total_test_duration:.2f} seconds")
    print(f"Overall Success Rate: {success_count}/100 ({success_count:.1f}%)")
    print(f"Overall Failures: {fail_count}")
    
    print("\nTiers Latency Breakdown:")
    print(f"  Tier 1 - Fast Path (Greetings, Hours, Location, FAQ Cache):")
    print(f"    Target:  < 1000 ms")
    print(f"    Average: {avg_fp:.1f} ms")
    print(f"    Minimum: {min_fp:.1f} ms")
    print(f"    Maximum: {max_fp:.1f} ms")
    print(f"    Success: {len(fp_successes)}/{len(fast_path_results)}")
    
    print(f"\n  Tier 2/3 - Normal LLM Inference (Reasoning Queue via Semaphore):")
    print(f"    Target:  Queue controlled, maintain container stability")
    print(f"    Average: {avg_llm / 1000.0:.2f} seconds")
    print(f"    Minimum: {min_llm / 1000.0:.2f} seconds")
    print(f"    Maximum: {max_llm / 1000.0:.2f} seconds")
    print(f"    Success: {len(llm_successes)}/{len(llm_results)}")
    
    print("\nResource Utilization Telemetry:")
    print(f"  CPU Utilization: Initial: {initial_health['system']['cpu_percent']}% -> Peak Load: {final_health['system']['cpu_percent']}%")
    print(f"  RAM Utilization: Initial: {initial_health['system']['ram_percent']}% -> Peak Load: {final_health['system']['ram_percent']}%")
    
    # Print fail errors if any
    fails = [r for r in results if not r["success"]]
    if fails:
        print("\nErrors encountered:")
        for i, f in enumerate(fails[:5]):
            print(f"  Error {i+1} [{f['type']}]: {f['error']}")
            
    print("======================================================================")

if __name__ == "__main__":
    asyncio.run(main())
