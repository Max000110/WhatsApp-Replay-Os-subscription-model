from sqlalchemy import text
from app.database import SessionLocal
import sys

def reseed():
    db = SessionLocal()
    try:
        # 1. Clean up any existing records with email 'sana@gmail.com' or tenant_id 'b99f7a4f-0007-4534-af01-5421109d3700'
        db.execute(text("DELETE FROM messages WHERE tenant_id = 'b99f7a4f-0007-4534-af01-5421109d3700'"))
        db.execute(text("DELETE FROM conversations WHERE tenant_id = 'b99f7a4f-0007-4534-af01-5421109d3700'"))
        db.execute(text("DELETE FROM chatbots WHERE tenant_id = 'b99f7a4f-0007-4534-af01-5421109d3700'"))
        db.execute(text("DELETE FROM whatsapp_sessions WHERE tenant_id = 'b99f7a4f-0007-4534-af01-5421109d3700'"))
        db.execute(text("DELETE FROM users WHERE email = 'sana@gmail.com'"))
        db.execute(text("DELETE FROM tenant_quotas WHERE tenant_id = 'b99f7a4f-0007-4534-af01-5421109d3700'"))
        db.execute(text("DELETE FROM subscriptions WHERE tenant_id = 'b99f7a4f-0007-4534-af01-5421109d3700'"))
        db.execute(text("DELETE FROM tenants WHERE id = 'b99f7a4f-0007-4534-af01-5421109d3700'"))
        db.commit()
        print("Cleaned up existing acceptance test records.")

        # 2. Insert Tenant Diag Test Corp (b99f7a4f-0007-4534-af01-5421109d3700)
        db.execute(text("""
            INSERT INTO tenants (id, name, subdomain, status, data_retention_policy, is_visible)
            VALUES ('b99f7a4f-0007-4534-af01-5421109d3700', 'Diag Test Corp', 'diagtest2', 'active', 'archive', true)
        """))
        print("Inserted Tenant.")

        # 2b. Insert Administrative Tenant System Operations (d0f62b2d-1111-2222-3333-444455556666)
        db.execute(text("DELETE FROM users WHERE email = 'admin@replyos.com'"))
        db.execute(text("DELETE FROM tenant_quotas WHERE tenant_id = 'd0f62b2d-1111-2222-3333-444455556666'"))
        db.execute(text("DELETE FROM subscriptions WHERE tenant_id = 'd0f62b2d-1111-2222-3333-444455556666'"))
        db.execute(text("DELETE FROM tenants WHERE id = 'd0f62b2d-1111-2222-3333-444455556666'"))
        db.execute(text("""
            INSERT INTO tenants (id, name, subdomain, status, data_retention_policy, is_visible)
            VALUES ('d0f62b2d-1111-2222-3333-444455556666', 'System Operations', 'admin', 'active', 'archive', true)
        """))
        print("Inserted Administrative Tenant.")

        # 3. Insert User sana@gmail.com
        db.execute(text("""
            INSERT INTO users (id, tenant_id, email, password_hash, role, is_active, must_change_password)
            VALUES (
                'c1a2b3c4-d5e6-4f7a-8b9c-0d1e2f3a4b5c',
                'b99f7a4f-0007-4534-af01-5421109d3700',
                'sana@gmail.com',
                '$2b$12$rpziS0GEjvaArVQd8yEMVubbly/EGZgKd7dLZjMAeFM0ioDXbt516',
                'owner',
                true,
                false
            )
        """))
        print("Inserted User sana@gmail.com.")

        # 3b. Insert Administrative User admin@replyos.com
        db.execute(text("""
            INSERT INTO users (id, tenant_id, email, password_hash, first_name, last_name, role, is_active, must_change_password)
            VALUES (
                'a1a2b3c4-d5e6-4f7a-8b9c-0d1e2f3a4b5d',
                'd0f62b2d-1111-2222-3333-444455556666',
                'admin@replyos.com',
                '$2b$12$XoNLu80bJRoe.JnsubL5i.B6HMXrpO11zMmhlo5KR8FyhzRmhc60O',
                'System',
                'Admin',
                'admin',
                true,
                false
            )
        """))
        print("Inserted Administrative User admin@replyos.com.")

        # 4. Insert Subscription
        db.execute(text("""
            INSERT INTO subscriptions (id, tenant_id, plan_tier, status, max_bots, max_messages_per_month)
            VALUES (
                '8c2b5d6f-789a-4c2b-9d41-3ef8a7c2e5b9',
                'b99f7a4f-0007-4534-af01-5421109d3700',
                'pro',
                'active',
                5,
                5000
            )
        """))
        print("Inserted Subscription.")

        # 5. Insert Tenant Quota
        db.execute(text("""
            INSERT INTO tenant_quotas (id, tenant_id, max_bots, max_messages, bots_used, messages_used)
            VALUES (
                'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
                'b99f7a4f-0007-4534-af01-5421109d3700',
                5,
                5000,
                1,
                0
            )
        """))
        print("Inserted Tenant Quota.")

        # 6. Insert WhatsApp Session
        db.execute(text("""
            INSERT INTO whatsapp_sessions (id, tenant_id, phone_number, session_name, status)
            VALUES (
                '7f12001c-d773-463d-b533-db2ad682b9cb',
                'b99f7a4f-0007-4534-af01-5421109d3700',
                '185654373789739',
                'Acceptance Test Session',
                'connected'
            )
        """))
        print("Inserted WhatsApp Session.")

        # 7. Insert Chatbot
        db.execute(text("""
            INSERT INTO chatbots (id, tenant_id, session_id, name, system_prompt, model_name, is_active, personality)
            VALUES (
                '66163546-4e56-410a-9f62-32c21179aa5e',
                'b99f7a4f-0007-4534-af01-5421109d3700',
                '7f12001c-d773-463d-b533-db2ad682b9cb',
                'Sana AI',
                'You are Sana AI. Answer user questions contextually.',
                'qwen2.5:1.5b-instruct',
                true,
                'Professional'
            )
        """))
        print("Inserted Chatbot.")

        # 8. Insert Conversation
        db.execute(text("""
            INSERT INTO conversations (id, tenant_id, session_id, customer_phone, customer_name, is_archived)
            VALUES (
                'f496e0c2-6c62-4c8d-91d1-00b490312597',
                'b99f7a4f-0007-4534-af01-5421109d3700',
                '7f12001c-d773-463d-b533-db2ad682b9cb',
                '185654373789739@lid',
                'Acceptance Client',
                false
            )
        """))
        print("Inserted Conversation.")

        db.commit()
        print("All database seed records successfully restored for acceptance tests!")
    except Exception as e:
        db.rollback()
        print("Error during seed restore:", e)
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    reseed()
