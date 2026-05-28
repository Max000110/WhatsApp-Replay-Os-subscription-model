import makeWASocket, { DisconnectReason, WASocket, useMultiFileAuthState, fetchLatestBaileysVersion } from "@whiskeysockets/baileys";
import { Boom } from "@hapi/boom";
import { Pool } from "pg";
import { usePostgresAuthState } from "./session-db-store";
import { AntiBanQueue } from "./anti-ban";
import pino from "pino";
import axios from "axios";

export class BaileysManager {
  private pool: Pool;
  private activeSockets: Map<string, WASocket> = new Map();
  private activeQueues: Map<string, AntiBanQueue> = new Map();
  private reconnectingSessions: Set<string> = new Set();
  private backendWebhookUrl: string;
  private redisUrl?: string;

  constructor(pool: Pool, backendWebhookUrl: string, redisUrl?: string) {
    this.pool = pool;
    this.backendWebhookUrl = backendWebhookUrl;
    this.redisUrl = redisUrl;
  }

  /**
   * Initializes or restores a WhatsApp Web connection session
   */
  public async initSession(sessionId: string): Promise<void> {
    if (this.activeSockets.has(sessionId)) {
      console.log(`[BaileysManager] Session ${sessionId} already active.`);
      return;
    }
    if (this.reconnectingSessions.has(sessionId)) {
      console.log(`[BaileysManager] Session ${sessionId} is already initializing or reconnecting.`);
      return;
    }

    console.log(`[BaileysManager] Starting session initialization: ${sessionId}`);
    const logger = pino({ level: "silent" });

    // Retrieve database-backed authentication credentials state
    const { state, saveCreds } = await usePostgresAuthState(this.pool, sessionId);

    // Fetch latest WhatsApp Web version dynamically to avoid 405/Outdated protocol rejection
    let version: any = [2, 3000, 1017539703]; // High fallback default version
    let isLatest = true;
    try {
      const latest = await fetchLatestBaileysVersion();
      version = latest.version;
      isLatest = latest.isLatest;
      console.log(`[BaileysManager - ${sessionId}] Dynamic WhatsApp Web version fetched: ${version.join(".")}, isLatest: ${isLatest}`);
    } catch (err: any) {
      console.warn(`[BaileysManager - ${sessionId}] Failed to fetch dynamic WhatsApp Web version, using fallback: ${version.join(".")}`, err.message);
    }

    // Initialize Baileys Socket Client
    const socket = makeWASocket({
      version,
      auth: state,
      printQRInTerminal: false,
      logger,
      browser: ["ReplyOS", "Chrome", "1.0.0"]
    });

    this.activeSockets.set(sessionId, socket);

    let tenantId = "unknown";
    try {
      const res = await this.pool.query("SELECT tenant_id FROM whatsapp_sessions WHERE id = $1", [sessionId]);
      if (res.rows.length > 0) {
        tenantId = res.rows[0].tenant_id;
      }
    } catch (err: any) {
      console.error(`[BaileysManager - ${sessionId}] Failed to query tenant_id:`, err.message);
    }

    // Bind safe Anti-Ban outbound queue scheduler with status callback
    const antiBan = new AntiBanQueue(socket, sessionId, tenantId, this.redisUrl, (event, data) => {
      this.notifyWebhook(sessionId, event, data);
    });
    this.activeQueues.set(sessionId, antiBan);

    // Handle credentials state updates
    socket.ev.on("creds.update", saveCreds);

    // Handle connection state and QR changes
    socket.ev.on("connection.update", async (update) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        console.log(`[BaileysManager - ${sessionId}] New QR Code generated.`);
        // Save QR back to database so NextJS frontend can stream it
        await this.pool.query(
          "UPDATE whatsapp_sessions SET status = $1, qr_code = $2, updated_at = NOW() WHERE id = $3",
          ["scanning", qr, sessionId]
        );
        this.notifyWebhook(sessionId, "qr", { qr });
      }

      if (connection === "open") {
        console.log(`[BaileysManager - ${sessionId}] Session connected successfully!`);
        
        // Grab connected phone number from JID
        const phone = socket.user?.id.split(":")[0] || null;
        
        await this.pool.query(
          "UPDATE whatsapp_sessions SET status = $1, qr_code = NULL, phone_number = $2, reconnect_attempts = 0, updated_at = NOW() WHERE id = $3",
          ["connected", phone, sessionId]
        );

        this.notifyWebhook(sessionId, "connected", { phone: phone || "" });
      }

      if (connection === "close") {
        const errorReason = (lastDisconnect?.error as Boom)?.output?.statusCode;
        console.log(`[BaileysManager - ${sessionId}] Connection closed. Reason code:`, errorReason);

        if (errorReason === DisconnectReason.loggedOut) {
          console.warn(`[BaileysManager - ${sessionId}] Logged out by WhatsApp server. Wiping auth keys.`);
          
          await this.pool.query(
            "UPDATE whatsapp_sessions SET status = $1, qr_code = NULL, session_auth_data = NULL, updated_at = NOW() WHERE id = $2",
            ["disconnected", sessionId]
          );

          await this.cleanupSession(sessionId);
          this.notifyWebhook(sessionId, "disconnected", { error: "logged_out" });
        } else {
          // Reconnect logic
          console.log(`[BaileysManager - ${sessionId}] Attempting to reconnect...`);
          
          await this.pool.query(
            "UPDATE whatsapp_sessions SET status = $1, reconnect_attempts = reconnect_attempts + 1, updated_at = NOW() WHERE id = $2",
            ["disconnected", sessionId]
          );

          await this.cleanupSession(sessionId);
          
          // Check reconnect limit to avoid infinite storming
          const limitRes = await this.pool.query(
            "SELECT reconnect_attempts FROM whatsapp_sessions WHERE id = $1",
            [sessionId]
          );
          const attempts = limitRes.rows[0]?.reconnect_attempts || 0;
          if (attempts > 5) {
            console.warn(`[BaileysManager - ${sessionId}] Max reconnect attempts reached (attempts: ${attempts}). Pausing automation.`);
            this.notifyWebhook(sessionId, "disconnected", { error: "max_reconnects_reached" });
            return;
          }

          this.reconnectingSessions.add(sessionId);
          
          // Reconnect with incremental jitter backoff delay to avoid server hammering (5s delay)
          setTimeout(() => {
            this.reconnectingSessions.delete(sessionId);
            this.initSession(sessionId).catch(err => {
              console.error(`[BaileysManager - ${sessionId}] Reconnect retry failed:`, err.message);
            });
          }, 5000);
        }
      }
    });

    // Capture incoming message events
    socket.ev.on("messages.upsert", async (m) => {
      if (m.type !== "notify") return;

      for (const msg of m.messages) {
        // Skip messages sent by the bot itself or status messages
        if (msg.key.fromMe || msg.key.remoteJid === "status@broadcast") continue;

        const remoteJid = msg.key.remoteJid;
        const from = remoteJid?.split("@")[0] || "";
        const pushName = msg.pushName || "";
        
        // Extract plain message body
        const body = msg.message?.conversation || 
                     msg.message?.extendedTextMessage?.text || 
                     msg.message?.imageMessage?.caption || 
                     "";

        // ── GUARD: skip delivery receipts, reactions, and libsignal Bad MAC events ──
        // When Baileys can't decrypt a frame (Bad MAC), it still fires the event
        // with an empty body string. Forwarding these to the backend creates ghost
        // inbound records and triggers the AI pipeline for non-messages.
        if (!body || !body.trim()) {
          console.log(`[BaileysManager - ${sessionId}] Skipping empty-body event from ${from} (receipt/reaction/decrypt error)`);
          continue;
        }

        console.log(`[BaileysManager - ${sessionId}] Incoming message from ${from}: "${body}"`);

        // Forward message payload via webhook to FastAPI backend router
        this.notifyWebhook(sessionId, "message", {
          messageId: msg.key.id || "",
          from,
          pushName,
          body,
          timestamp: Number(msg.messageTimestamp) || Math.floor(Date.now() / 1000)
        });
      }
    });

    // Capture message status / ACK update events
    socket.ev.on("messages.update", async (updates) => {
      for (const update of updates) {
        if (!update.key || !update.update) continue;
        
        const messageId = update.key.id;
        const from = update.key.remoteJid?.split("@")[0] || "";
        const statusVal = update.update.status;
        
        if (statusVal === undefined || statusVal === null) continue;
        
        // Map Baileys numeric status to our string states
        let stringStatus = "sent";
        if (statusVal === 3) {
          stringStatus = "delivered";
        } else if (statusVal === 4 || statusVal === 5) {
          stringStatus = "read";
        } else if (statusVal === 2) {
          stringStatus = "sent";
        } else if (statusVal === 1) {
          stringStatus = "sending";
        } else {
          continue; // Ignore other statuses like PENDING/PLAYED if not mapped
        }

        console.log(`[BaileysManager - ${sessionId}] Message status update: ${messageId} -> ${stringStatus}`);

        // Forward ACK update to FastAPI backend webhook
        this.notifyWebhook(sessionId, "ack", {
          whatsappMessageId: messageId,
          from,
          status: stringStatus
        });
      }
    });

  }

  /**
   * Safe message dispatcher leveraging anti-ban queue
   */
  public async queueOutgoingMessage(sessionId: string, to: string, text: string, messageId?: string): Promise<boolean> {
    const queue = this.activeQueues.get(sessionId);
    if (!queue) {
      console.error(`[BaileysManager] Session ${sessionId} does not have an active queue. Initializing first.`);
      await this.initSession(sessionId);
      const reFetchedQueue = this.activeQueues.get(sessionId);
      if (!reFetchedQueue) return false;
      await reFetchedQueue.queueMessage(to, text, messageId);
      return true;
    }

    await queue.queueMessage(to, text, messageId);
    return true;
  }

  /**
   * Helper sending structured HTTP webhook updates back to backend services
   */
  private async notifyWebhook(sessionId: string, event: string, data: any) {
    try {
      await axios.post(this.backendWebhookUrl, {
        sessionId,
        event,
        data
      }, {
        headers: { "Content-Type": "application/json" },
        timeout: 5000
      });
    } catch (error: any) {
      console.error(`[BaileysManager - ${sessionId}] Webhook payload transmission failed:`, error.message);
    }
  }

  private async cleanupSession(sessionId: string) {
    const socket = this.activeSockets.get(sessionId);
    if (socket) {
      try {
        console.log(`[BaileysManager - ${sessionId}] Gracefully terminating old socket connection...`);
        socket.ev.removeAllListeners("connection.update");
        socket.ev.removeAllListeners("creds.update");
        socket.ev.removeAllListeners("messages.upsert");
        socket.end(undefined);
      } catch (err: any) {
        console.error(`[BaileysManager - ${sessionId}] Error closing active socket:`, err.message);
      }
      this.activeSockets.delete(sessionId);
    }
    const queue = this.activeQueues.get(sessionId);
    if (queue) {
      await queue.disconnect();
      this.activeQueues.delete(sessionId);
    }
  }

  public getActiveSessionCount(): number {
    return this.activeSockets.size;
  }
}
