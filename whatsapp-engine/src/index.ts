import express from "express";
import cors from "cors";
import { Pool } from "pg";
import { BaileysManager } from "./baileys-manager";

const app = express();
const port = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());

// Initialize PostgreSQL Connection Pool
const pool = new Pool({
  connectionString: process.env.DATABASE_URL
});

// Grab endpoint routing configs from environment
const backendWebhookUrl = process.env.BACKEND_API_URL || "http://backend:8000/api/v1/sessions/webhook";
const redisUrl = process.env.REDIS_URL || undefined;

// Create singleton Baileys session coordinator
const baileysManager = new BaileysManager(pool, backendWebhookUrl, redisUrl);

// REST Router: Spin up or restore session
app.post("/sessions/init", async (req, res) => {
  const { sessionId } = req.body;
  if (!sessionId) {
    return res.status(400).json({ error: "sessionId is required" });
  }

  try {
    // Initiate background connection (runs asynchronously in event loop)
    baileysManager.initSession(sessionId).catch(err => {
      console.error(`[Express] Error starting session ${sessionId}:`, err.message);
    });
    
    return res.status(202).json({ status: "initializing", message: "Connection process started in background." });
  } catch (error: any) {
    return res.status(500).json({ error: error.message });
  }
});

// REST Router: Send/Queue outbound WhatsApp messages
app.post("/sessions/send", async (req, res) => {
  const { sessionId, to, text, messageId } = req.body;
  if (!sessionId || !to || !text) {
    return res.status(400).json({ error: "sessionId, to, and text are required fields" });
  }

  try {
    const success = await baileysManager.queueOutgoingMessage(sessionId, to, text, messageId);
    if (success) {
      return res.status(200).json({ status: "queued", message: "Message added to outbound anti-ban queue." });
    } else {
      return res.status(500).json({ error: "Failed to queue message. Session might not be initialized." });
    }
  } catch (error: any) {
    return res.status(500).json({ error: error.message });
  }
});

// REST Router: Service Diagnostics & Heartbeat
app.get("/health", (req, res) => {
  return res.status(200).json({
    status: "healthy",
    activeSessions: baileysManager.getActiveSessionCount()
  });
});

// Initialize existing sessions stored in database upon container boot
async function restoreSessions() {
  try {
    const res = await pool.query(
      "SELECT id FROM whatsapp_sessions WHERE status IN ('connected', 'scanning')"
    );
    console.log(`[Express] Found ${res.rows.length} sessions to restore.`);
    for (const row of res.rows) {
      baileysManager.initSession(row.id).catch(err => {
        console.error(`[Express] Restore failed for session ${row.id}:`, err.message);
      });
    }
  } catch (error: any) {
    console.error("[Express] Failed restoring sessions on boot:", error.message);
  }
}

app.listen(port, () => {
  console.log(`[Express] WhatsApp Control Engine listening on port ${port}`);
  restoreSessions();
});
