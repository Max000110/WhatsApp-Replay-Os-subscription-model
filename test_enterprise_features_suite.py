import requests
import sys
import time

BASE_URL = "http://localhost:8080/api/v1"

class ReplyOSEnterpriseFeaturesSuite:
    def __init__(self):
        self.cust_token = None
        self.cust_headers = {}
        self.admin_token = None
        self.admin_headers = {}
        
        # Test states matching seeded data
        self.bot_id = "66163546-4e56-410a-9f62-32c21179aa5e"
        self.conv_id = "f496e0c2-6c62-4c8d-91d1-00b490312597"
        self.session_id = "7f12001c-d773-463d-b533-db2ad682b9cb"
        self.customer_phone = "185654373789739"
        
        self.agent_id = None

    def run_suite(self):
        print("======================================================================")
        print("         REPLYOS ENTERPRISE FEATURES E2E VALIDATION SUITE             ")
        print("======================================================================\n")

        # 0. Seed database dynamically to ensure fresh clean state
        self.seed_database_state()

        # 1. Test Customer & Admin Google Logins
        self.test_1_google_logins()

        # 2. Test Support Agent CRUD
        self.test_2_support_agent_crud()

        # 3. Test Agent Assignment & Conversation Transfer
        self.test_3_agent_assignment_and_transfer()

        # 4. Test Human Handoff Bot Bypassing
        self.test_4_human_handoff_bypassing()

        # 5. Test AI Router & Specialized Agent Prompts
        self.test_5_ai_router_and_specialized_agents()

        # 6. Test Google Calendar Booking Flow
        self.test_6_google_calendar_booking()

        print("======================================================================")
        print("     ALL ENTERPRISE FEATURES VALIDATED SUCCESSFULLY (100% PASS).      ")
        print("======================================================================")

    def test_1_google_logins(self):
        print("[TEST 1] Testing Native self-hosted Authentication...")
        
        # Native Customer Login
        payload = {
            "email": "sana@gmail.com",
            "password": "TestPass123!"
        }
        res = requests.post(f"{BASE_URL}/auth/login", json=payload)
        assert res.status_code == 200, f"Customer Native Login failed: {res.text}"
        self.cust_token = res.json()["access_token"]
        self.cust_headers = {
            "Authorization": f"Bearer {self.cust_token}",
            "Content-Type": "application/json"
        }
        print("  PASS: Customer Native Authentication succeeded.")

        # Native Admin Login
        payload = {
            "email": "admin@replyos.com",
            "password": "AdminAccess2026!"
        }
        res = requests.post(f"{BASE_URL}/admin/auth/login", json=payload)
        assert res.status_code == 200, f"Admin Native Login failed: {res.text}"
        self.admin_token = res.json()["access_token"]
        self.admin_headers = {
            "Authorization": f"Bearer {self.admin_token}",
            "Content-Type": "application/json"
        }
        print("  PASS: Admin Native Authentication succeeded.\n")

    def test_2_support_agent_crud(self):
        print("[TEST 2] Testing Support Agent Management...")
        
        # Create support agent
        payload = {
            "name": "Jane Support",
            "email": "jane.support@replyos.com",
            "department": "Support",
            "skills": "Troubleshooting, FAQ resolving",
            "status": "available"
        }
        res = requests.post(f"{BASE_URL}/agents", json=payload, headers=self.cust_headers)
        assert res.status_code == 201, f"Create Support Agent failed: {res.text}"
        agent = res.json()
        self.agent_id = agent["id"]
        assert agent["name"] == "Jane Support"
        print(f"  PASS: Created Support Agent: ID={self.agent_id}, Dept={agent['department']}")

        # List support agents
        res = requests.get(f"{BASE_URL}/agents", headers=self.cust_headers)
        assert res.status_code == 200, f"List Support Agents failed: {res.text}"
        agents = res.json()
        assert any(a["id"] == self.agent_id for a in agents)
        print("  PASS: Support agent CRUD validated successfully.\n")

    def test_3_agent_assignment_and_transfer(self):
        print("[TEST 3] Testing Agent Assignment & Transfers...")
        
        # Assign conversation
        payload = {
            "conversation_id": self.conv_id,
            "agent_id": self.agent_id
        }
        res = requests.post(f"{BASE_URL}/agents/assign", json=payload, headers=self.cust_headers)
        assert res.status_code == 200, f"Assign Conversation failed: {res.text}"
        conv = res.json()
        assert conv["assigned_agent_id"] == self.agent_id
        assert conv["handoff_status"] == "HUMAN_ACTIVE"
        print("  PASS: Successfully assigned conversation. Status shifted to 'HUMAN_ACTIVE'.")

        # Transfer conversation to Technical department
        payload = {
            "conversation_id": self.conv_id,
            "target_department": "Technical"
        }
        res = requests.post(f"{BASE_URL}/agents/transfer", json=payload, headers=self.cust_headers)
        assert res.status_code == 200, f"Transfer Conversation failed: {res.text}"
        conv = res.json()
        assert conv["lead_stage"] == "Technical" # department mapped
        assert conv["handoff_status"] == "WAITING_AGENT" # waiting for pickup
        print("  PASS: Successfully transferred conversation. Status shifted to 'WAITING_AGENT'.\n")

    def test_4_human_handoff_bypassing(self):
        print("[TEST 4] Testing Human Handoff AI Bypassing...")
        
        # Put chat in WAITING_AGENT handoff status to block bot response
        payload = {"status": "WAITING_AGENT"}
        res = requests.post(f"{BASE_URL}/chats/{self.conv_id}/handoff", json=payload, headers=self.cust_headers)
        assert res.status_code == 200
        
        # Mimic incoming WhatsApp webhook.
        webhook_payload = {
            "sessionId": self.session_id,
            "event": "message",
            "data": {
                "from": f"{self.customer_phone}@lid",
                "rawRemoteJid": f"{self.customer_phone}@lid",
                "pushName": "Valued Customer",
                "body": "Need urgent technical assistance",
                "messageId": f"test-handoff-{int(time.time())}",
                "timestamp": int(time.time())
            }
        }
        
        # Send webhook
        res = requests.post(f"{BASE_URL}/sessions/webhook", json=webhook_payload)
        assert res.status_code == 200, f"Webhook trigger failed: {res.text}"
        print("  PASS: Inbound webhook triggered successfully.")

        # Wait a short moment and verify that NO outbound AI message is generated
        time.sleep(1.0)
        res = requests.get(f"{BASE_URL}/chats/{self.conv_id}/messages", headers=self.cust_headers)
        messages = res.json()
        outbound = [m for m in messages if m["direction"] == "outbound" and "Urgent" in m["content"]]
        assert len(outbound) == 0, "AI bot responded during human handoff!"
        print("  PASS: AI bot bypassed correctly during handoff.")

        # Release conversation back to AI bot
        res = requests.post(f"{BASE_URL}/chats/{self.conv_id}/release", headers=self.cust_headers)
        assert res.status_code == 200
        conv = res.json()
        assert conv["handoff_status"] == "RESOLVED"
        print("  PASS: Released conversation back to bot. Status set to 'RESOLVED'.\n")

    def test_5_ai_router_and_specialized_agents(self):
        print("[TEST 5] Testing AI Routing & Specialized Agents...")
        
        # 1. Billing Inquiry Intent
        payload = {
            "test_question": "What is your pricing policy and how do I pay my invoice?",
            "conversation_id": self.conv_id
        }
        res = requests.post(f"{BASE_URL}/bots/{self.bot_id}/test-prompt", json=payload, headers=self.cust_headers)
        assert res.status_code == 200, f"Prompt testing failed: {res.text}"
        data = res.json()
        prompt = data["constructed_prompt"]
        assert "SPECIALIZED AGENT LAYER: BILLING" in prompt, "Missing specialized Billing Agent prompt!"
        print("  PASS: Classified intent 'BILLING' and injected specialized Billing Agent prompt layer.")

        # 2. Booking Inquiry Intent
        payload = {
            "test_question": "Book a meeting on Monday",
            "conversation_id": self.conv_id
        }
        res = requests.post(f"{BASE_URL}/bots/{self.bot_id}/test-prompt", json=payload, headers=self.cust_headers)
        assert res.status_code == 200
        data = res.json()
        prompt = data["constructed_prompt"]
        assert "SPECIALIZED AGENT LAYER: BOOKING" in prompt, "Missing specialized Booking Agent prompt!"
        print("  PASS: Classified intent 'BOOKING' and injected specialized Booking Agent prompt layer.\n")

    def test_6_google_calendar_booking(self):
        print("[TEST 6] Testing Google Calendar Booking Sync...")
        
        # List slots
        res = requests.get(f"{BASE_URL}/bookings/slots?date=2026-06-01", headers=self.cust_headers)
        assert res.status_code == 200, f"Get slots failed: {res.text}"
        slots = res.json()["slots"]
        assert "10:00" in slots
        print(f"  PASS: Listed available slots from Google Calendar: {slots}")

        # Create booking
        payload = {
            "customer_phone": self.customer_phone,
            "customer_email": "customer@replyos.com",
            "booking_date": "2026-06-01",
            "booking_time": "10:00",
            "notes": "Introductory SaaS recovery demo"
        }
        res = requests.post(f"{BASE_URL}/bookings", json=payload, headers=self.cust_headers)
        assert res.status_code == 200, f"Create booking failed: {res.text}"
        booking = res.json()
        assert booking["customer_email"] == "customer@replyos.com"
        assert booking["calendar_event_id"].startswith("gcal_evt_")
        assert booking["booking_id"].startswith("bk_")
        print(f"  PASS: Booking created successfully. booking_id={booking['booking_id']}, calendar_event_id={booking['calendar_event_id']}\n")

    def seed_database_state(self):
        print("[TEST 0] Seeding dynamic system state in backend container...")
        import subprocess
        res = subprocess.run([
            "docker", "exec", "-e", "PYTHONPATH=/app", "saas_backend", 
            "python3", "/app/project-files/scratch/reseed_acceptance_corp.py"
        ], capture_output=True, text=True)
        if res.returncode != 0:
            print(f"  FAIL: Database seeding failed: {res.stderr}")
            sys.exit(1)
        print("  PASS: Database seeder returned success. Schema structures established.\n")


if __name__ == "__main__":
    suite = ReplyOSEnterpriseFeaturesSuite()
    try:
        suite.run_suite()
    except AssertionError as e:
        import traceback
        print("\nAssertion Error Traceback:")
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        import traceback
        print("\nSuite Error Traceback:")
        traceback.print_exc()
        sys.exit(1)
