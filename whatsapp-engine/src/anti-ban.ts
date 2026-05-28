import { WASocket } from "@whiskeysockets/baileys";
import { createClient } from "redis";
import { QueueMessage } from "./types";

export class AntiBanQueue {
  private socket: WASocket;
  private redisClient: ReturnType<typeof createClient> | null = null;
  private sessionId: string;
  private tenantId: string;
  private isProcessing = false;
  private redisQueueKey: string;
  private onStatusUpdate?: (event: string, data: any) => void;

  constructor(socket: WASocket, sessionId: string, tenantId: string, redisUrl?: string, onStatusUpdate?: (event: string, data: any) => void) {
    this.socket = socket;
    this.sessionId = sessionId;
    this.tenantId = tenantId;
    this.redisQueueKey = `whatsapp_queue_${sessionId}`;
    this.onStatusUpdate = onStatusUpdate;

    if (redisUrl) {
      this.redisClient = createClient({ url: redisUrl });
      this.redisClient.connect().catch((err) => {
        console.error(`[AntiBanQueue - ${sessionId}] Failed to connect to Redis:`, err.message);
      });
    }
  }

  /**
   * Pushes outbound message safely to Redis queues or dispatches immediately
   */
  public async queueMessage(to: string, text: string, messageId?: string, options: { simulateTyping?: boolean } = {}) {
    // Robust JID normalization supporting both raw numbers and pre-formatted JIDs
    let cleanJid = to.trim().replace(/\s+/g, "").replace("+", "");
    if (!cleanJid.endsWith("@s.whatsapp.net") && !cleanJid.includes("@")) {
      cleanJid = `${cleanJid}@s.whatsapp.net`;
    }

    const payload: QueueMessage = {
      sessionId: this.sessionId,
      to: cleanJid,
      text,
      simulateTyping: options.simulateTyping ?? true,
      messageId
    };

    if (this.redisClient && this.redisClient.isOpen) {
      await this.redisClient.rPush(this.redisQueueKey, JSON.stringify(payload));
      this.triggerQueueWorker();
    } else {
      // Fallback to immediate safe dispatch in case Redis is temporarily disconnected
      console.warn(`[AntiBanQueue - ${this.sessionId}] Redis offline. Sending immediately.`);
      this.dispatchSafeMessage(payload);
    }
  }

  private async triggerQueueWorker() {
    if (this.isProcessing) return;
    this.isProcessing = true;

    try {
      while (this.redisClient && this.redisClient.isOpen) {
        const item = await this.redisClient.lPop(this.redisQueueKey);
        if (!item) break;

        const payload: QueueMessage = JSON.parse(item);
        await this.dispatchSafeMessage(payload);
      }
    } catch (error: any) {
      console.error(`[AntiBanQueue - ${this.sessionId}] Worker error:`, error.message);
    } finally {
      this.isProcessing = false;
    }
  }

  /**
   * Internal mechanism sending standard message with realistic pauses
   */
  private async dispatchSafeMessage(payload: QueueMessage) {
    const jid = payload.to;
    const text = payload.text;
    const messageId = payload.messageId;

    try {
      if (messageId && this.onStatusUpdate) {
        this.onStatusUpdate("ack", { messageId, status: "sending" });
      }

      if (payload.simulateTyping) {
        // Trigger simulated typing indicator
        await this.socket.sendPresenceUpdate("composing", jid);

        // Simulated speed latency: ~20ms per character, capped at 3.5s to remain fluid
        const typingDelay = Math.min(Math.max(text.length * 20, 600), 3500);
        await new Promise((resolve) => setTimeout(resolve, typingDelay));

        // Disable indicator
        await this.socket.sendPresenceUpdate("paused", jid);
      }

      // Dynamic jitter delay to avoid signature automation footprints (4s - 8s)
      const safetyInterval = Math.floor(Math.random() * 4000) + 4000;
      await new Promise((resolve) => setTimeout(resolve, safetyInterval));

      console.log(`[AntiBanQueue - ${this.sessionId}] BEFORE socket.sendMessage:`, {
        tenant_id: this.tenantId,
        session_id: this.sessionId,
        jid,
        message_id: messageId || null,
        message_body: text,
        socket_state: this.socket ? "connected" : "disconnected",
        dispatch_source: "AntiBanQueue"
      });

      const messageResult = await this.socket.sendMessage(jid, { text });
      
      console.log(`[AntiBanQueue - ${this.sessionId}] AFTER socket.sendMessage:`, {
        tenant_id: this.tenantId,
        session_id: this.sessionId,
        jid,
        message_id: messageId || null,
        message_body: text,
        socket_state: this.socket ? "connected" : "disconnected",
        message_result_id: messageResult?.key?.id || null,
        dispatch_source: "AntiBanQueue"
      });

      if (messageId && this.onStatusUpdate && messageResult) {
        this.onStatusUpdate("ack", {
          messageId,
          whatsappMessageId: messageResult.key.id,
          status: "sent"
        });
      }
    } catch (err: any) {
      console.error(`[AntiBanQueue - ${this.sessionId}] Failed safe dispatch:`, err.message);
      if (messageId && this.onStatusUpdate) {
        this.onStatusUpdate("ack", {
          messageId,
          status: "failed",
          error: err.message
        });
      }
    }
  }

  public async disconnect() {
    if (this.redisClient && this.redisClient.isOpen) {
      await this.redisClient.disconnect();
    }
  }
}
