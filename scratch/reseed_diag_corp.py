from sqlalchemy import text
from app.database import SessionLocal
import sys

def reseed():
    db = SessionLocal()
    try:
        # 1. Clean up any existing subdomain 'diagtest' or email 'diagtest2@example.com'
        db.execute(text("DELETE FROM users WHERE email = 'diagtest2@example.com'"))
        db.execute(text("DELETE FROM tenants WHERE subdomain = 'diagtest'"))
        db.commit()
        print("Cleaned up existing diagtest records.")

        # 2. Insert Tenant Diag Test Corp
        db.execute(text("""
            INSERT INTO tenants (id, name, subdomain, status, data_retention_policy, is_visible)
            VALUES ('9b292a3c-c71f-490b-a92e-965511f1decb', 'Diag Test Corp', 'diagtest', 'active', 'archive', true)
        """))
        print("Inserted Tenant Diag Test Corp.")

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

        # 3. Insert User diagtest2@example.com
        db.execute(text("""
            INSERT INTO users (id, tenant_id, email, password_hash, role, is_active, must_change_password)
            VALUES (
                'e5844388-9362-4d87-bc7d-9a9a666592ef',
                '9b292a3c-c71f-490b-a92e-965511f1decb',
                'diagtest2@example.com',
                '$2b$12$rpziS0GEjvaArVQd8yEMVubbly/EGZgKd7dLZjMAeFM0ioDXbt516',
                'owner',
                true,
                false
            )
        """))
        print("Inserted User diagtest2@example.com.")

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
                '3d3a016f-124b-4a49-9d78-2df829b53112',
                '9b292a3c-c71f-490b-a92e-965511f1decb',
                'starter',
                'active',
                2,
                2000
            )
        """))
        print("Inserted Subscription.")

        # 5. Insert Chatbot
        db.execute(text("""
            INSERT INTO chatbots (id, tenant_id, name, system_prompt, model_name, is_active, memory_enabled)
            VALUES (
                '7f6e1078-de20-4265-8d9a-22c7f26e9d5f',
                '9b292a3c-c71f-490b-a92e-965511f1decb',
                'validation-bot',
                'You are a validation bot.',
                'qwen2.5:1.5b-instruct',
                true,
                true
            )
        """))
        print("Inserted Chatbot.")

        # 6. Insert Conversation
        db.execute(text("""
            INSERT INTO conversations (id, tenant_id, customer_phone, customer_name, is_archived)
            VALUES (
                '5eeaf42e-df8d-479e-ae83-d268381f6ff9',
                '9b292a3c-c71f-490b-a92e-965511f1decb',
                '917021886525',
                'Diag Customer',
                false
            )
        """))
        print("Inserted Conversation.")

        db.commit()
        print("All database seed records successfully restored!")
    except Exception as e:
        db.rollback()
        print("Error during seed restore:", e)
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    reseed()
