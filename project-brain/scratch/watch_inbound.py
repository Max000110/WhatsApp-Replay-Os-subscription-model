import time
import psycopg2
from psycopg2.extras import DictCursor

DATABASE_URL = "postgresql://saas_admin:SecretSaaSPassword123!@localhost:5432/saas_whatsapp"
CUSTOMER_JID = "917021886525@s.whatsapp.net"

def watch():
    print(f"[*] Starting live watcher for JID: {CUSTOMER_JID}")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    
    last_checked_msg_id = None
    
    # Get last message id to start watching from
    with conn.cursor(cursor_factory=DictCursor) as cur:
        cur.execute("SELECT id FROM messages ORDER BY created_at DESC LIMIT 1")
        row = cur.fetchone()
        if row:
            last_checked_msg_id = row['id']
            print(f"[*] Watching messages table starting after ID: {last_checked_msg_id}")
            
    try:
        while True:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(
                    "SELECT m.*, c.customer_phone FROM messages m "
                    "JOIN conversations c ON m.conversation_id = c.id "
                    "WHERE m.created_at > (SELECT created_at FROM messages WHERE id = %s) "
                    "ORDER BY m.created_at ASC",
                    (last_checked_msg_id,)
                )
                rows = cur.fetchall()
                for row in rows:
                    last_checked_msg_id = row['id']
                    print("\n" + "="*80)
                    print(f"[*] NEW MESSAGE DETECTED!")
                    print(f"ID: {row['id']}")
                    print(f"Conversation ID: {row['conversation_id']}")
                    print(f"Customer JID: {row['customer_phone']}")
                    print(f"Direction: {row['direction']}")
                    print(f"Sender Type: {row['sender_type']}")
                    print(f"Content: {row['content']}")
                    print(f"Status: {row['status']}")
                    print(f"ACK State: {row['ack_state']}")
                    print(f"WhatsApp Message ID: {row['whatsapp_message_id']}")
                    print(f"Created At: {row['created_at']}")
                    print("="*80 + "\n")
            time.sleep(1)
    except KeyboardInterrupt:
        print("[*] Watcher stopped.")
    finally:
        conn.close()

if __name__ == "__main__":
    watch()
