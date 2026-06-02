import { AuthenticationState, AuthenticationCreds, initAuthCreds, BufferJSON } from "@whiskeysockets/baileys";
import { Pool } from "pg";
import crypto from "crypto";

const ENCRYPTION_KEY = process.env.JWT_SECRET || "VeryStrongJWTSecret987654321!";
const ALGORITHM = "aes-256-gcm";

function encrypt(text: string): string {
  const key = crypto.createHash("sha256").update(ENCRYPTION_KEY).digest();
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv(ALGORITHM, key, iv);
  let encrypted = cipher.update(text, "utf8", "hex");
  encrypted += cipher.final("hex");
  const authTag = cipher.getAuthTag().toString("hex");
  return `${iv.toString("hex")}:${encrypted}:${authTag}`;
}

function decrypt(cipherText: string): string {
  const parts = cipherText.split(":");
  if (parts.length !== 3) {
    throw new Error("Invalid cipher text format");
  }
  const iv = Buffer.from(parts[0], "hex");
  const encrypted = Buffer.from(parts[1], "hex");
  const authTag = Buffer.from(parts[2], "hex");
  const key = crypto.createHash("sha256").update(ENCRYPTION_KEY).digest();
  const decipher = crypto.createDecipheriv(ALGORITHM, key, iv);
  decipher.setAuthTag(authTag);
  let decrypted = decipher.update(encrypted, undefined, "utf8");
  decrypted += decipher.final("utf8");
  return decrypted;
}

/**
 * Custom PostgreSQL Multi-Session State provider for Baileys.
 * Serializes, encrypts, and persists keys/creds inside a single JSONB column.
 */
export async function usePostgresAuthState(pool: Pool, sessionId: string): Promise<{ state: AuthenticationState, saveCreds: () => Promise<void> }> {
  // Fetch existing session auth data from database
  const res = await pool.query(
    "SELECT session_auth_data FROM whatsapp_sessions WHERE id = $1",
    [sessionId]
  );

  let sessionData: any = null;
  if (res.rows.length > 0 && res.rows[0].session_auth_data) {
    const rawRecord = res.rows[0].session_auth_data;
    
    // Transparent decryption with backward-compatible fallback
    if (rawRecord && rawRecord.encrypted === true && typeof rawRecord.data === "string") {
      try {
        const decryptedStr = decrypt(rawRecord.data);
        sessionData = JSON.parse(decryptedStr, BufferJSON.reviver);
      } catch (err: any) {
        console.error(`[PostgresAuthState - ${sessionId}] Decryption failed:`, err.message);
      }
    } else {
      // Legacy unencrypted data: read directly and mark for encryption on next write
      const rawData = JSON.stringify(rawRecord);
      sessionData = JSON.parse(rawData, BufferJSON.reviver);
    }
  }

  const creds: AuthenticationCreds = sessionData?.creds || initAuthCreds();
  const keys: { [key: string]: any } = sessionData?.keys || {};

  const saveState = async () => {
    const dataString = JSON.stringify({ creds, keys }, BufferJSON.replacer);
    
    // Encrypt serialized payload
    const encryptedData = encrypt(dataString);
    const databasePayload = {
      encrypted: true,
      data: encryptedData
    };

    await pool.query(
      "UPDATE whatsapp_sessions SET session_auth_data = $1, updated_at = NOW() WHERE id = $2",
      [databasePayload, sessionId]
    );
  };

  return {
    state: {
      creds,
      keys: {
        get: (type, ids) => {
          const data: { [id: string]: any } = {};
          for (const id of ids) {
            let value = keys[`${type}-${id}`];
            if (value) {
              if (type === "app-state-sync-key" && value.buffer) {
                value = Buffer.from(value.buffer);
              }
              data[id] = value;
            }
          }
          return data;
        },
        set: async (data: any) => {
          for (const category in data) {
            for (const id in data[category]) {
              const value = data[category][id];
              const key = `${category}-${id}`;
              if (value) {
                keys[key] = value;
              } else {
                delete keys[key];
              }
            }
          }
          await saveState();
        }
      }
    },
    saveCreds: async () => {
      await saveState();
    }
  };
}
