import { AuthenticationState, AuthenticationCreds, SignalDataTypeMap, initAuthCreds, BufferJSON } from "@whiskeysockets/baileys";
import { Pool } from "pg";

/**
 * Custom PostgreSQL Multi-Session State provider for Baileys.
 * Serializes and persists keys/creds inside a single JSONB column, enabling stateless containers.
 */
export async function usePostgresAuthState(pool: Pool, sessionId: string): Promise<{ state: AuthenticationState, saveCreds: () => Promise<void> }> {
  // Fetch existing session auth data from database
  const res = await pool.query(
    "SELECT session_auth_data FROM whatsapp_sessions WHERE id = $1",
    [sessionId]
  );

  let sessionData: any = null;
  if (res.rows.length > 0 && res.rows[0].session_auth_data) {
    // Parse using BufferJSON to recover typed buffers
    const rawData = JSON.stringify(res.rows[0].session_auth_data);
    sessionData = JSON.parse(rawData, BufferJSON.reviver);
  }

  const creds: AuthenticationCreds = sessionData?.creds || initAuthCreds();
  const keys: { [key: string]: any } = sessionData?.keys || {};

  const saveState = async () => {
    const dataString = JSON.stringify({ creds, keys }, BufferJSON.replacer);
    const dataJson = JSON.parse(dataString);

    await pool.query(
      "UPDATE whatsapp_sessions SET session_auth_data = $1, updated_at = NOW() WHERE id = $2",
      [dataJson, sessionId]
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
