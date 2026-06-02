import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://saas_admin:saas_admin_pass@postgres:5432/saas_whatsapp")

def merge_duplicate_conversations():
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        print("[Migration] Starting conversation deduplication and merging...")

        # 1. We want to identify the companion device JIDs (like 185654373789739@s.whatsapp.net)
        # and resolve them to their clean canonical JIDs (18565437378@s.whatsapp.net).
        # Let's fetch all conversations
        res = session.execute(text("SELECT id, customer_phone, tenant_id, session_id FROM conversations;")).fetchall()
        
        # Build map of clean phone to canonical conversation row
        phone_map = {}
        for row in res:
            conv_id, phone, tenant_id, session_id = row
            # Extract digits and check if it contains companion device digits appended
            clean_digits = phone.split("@")[0]
            
            # If the phone length is 15 and starts with 18565437378, it is a duplicate of 18565437378
            # E.g. "185654373789739" -> companion "18565437378" + "9739"
            canonical_phone = phone
            if len(clean_digits) == 15 and clean_digits.startswith("18565437378"):
                canonical_phone = "18565437378@s.whatsapp.net"
                print(f"[Migration] Mapping duplicate companion JID '{phone}' to canonical '{canonical_phone}'")
                
            if canonical_phone not in phone_map:
                phone_map[canonical_phone] = []
            phone_map[canonical_phone].append((conv_id, phone, tenant_id, session_id))

        # 2. Iterate and merge duplicates
        for canonical_phone, rows in phone_map.items():
            if len(rows) > 1:
                # Determine canonical row (the one that already has the canonical JID, or the oldest one)
                canonical_row = None
                for row in rows:
                    if row[1] == canonical_phone:
                        canonical_row = row
                        break
                if not canonical_row:
                    # Fallback to the first one
                    canonical_row = rows[0]
                    
                canonical_id = canonical_row[0]
                print(f"[Migration] Canonical conversation for '{canonical_phone}' is {canonical_id}")
                
                # Merge other rows into the canonical one
                for row in rows:
                    dup_id = row[0]
                    if dup_id == canonical_id:
                        continue
                        
                    print(f"[Migration] Merging duplicate conversation {dup_id} into canonical {canonical_id}...")
                    
                    # Move all messages to canonical conversation
                    session.execute(
                        text("UPDATE messages SET conversation_id = :canonical_id WHERE conversation_id = :dup_id"),
                        {"canonical_id": canonical_id, "dup_id": dup_id}
                    )
                    
                    # Delete the duplicate conversation
                    session.execute(
                        text("DELETE FROM conversations WHERE id = :dup_id"),
                        {"dup_id": dup_id}
                    )
                    
                # Update customer_phone on canonical conversation just in case it wasn't normalized
                session.execute(
                    text("UPDATE conversations SET customer_phone = :canonical_phone WHERE id = :canonical_id"),
                    {"canonical_phone": canonical_phone, "canonical_id": canonical_id}
                )

        session.commit()
        print("[Migration] Deduplication and merge finished successfully!")
    except Exception as e:
        session.rollback()
        print(f"[Migration] Error occurred during merge: {e}")
        raise e
    finally:
        session.close()

if __name__ == "__main__":
    merge_duplicate_conversations()
