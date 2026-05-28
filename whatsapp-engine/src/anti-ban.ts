import { WASocket } from "@whiskeysockets/baileys";
import { createClient } from "redis";
import { QueueMessage } from "./types";

export class AntiBanQueue {
  private socket: WASocket;
  private redisClient: ReturnType<typeof createClient> | null = null;
  private sessionId: string;
  private isProcessing = false;
  private redisQueueKey: string;

  constructor(socket: WASocket, sessionId: string, redisUrl?: string) {
    this.socket = socket;
    this.sessionId = sessionId;
    this.redisQueueKey = `whatsapp_queue_${sessionId}`;

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
  public async queueMessage(to: string, text: string, options: { simulateTyping?: boolean } = {}) {
    // Robust JID normalization supporting both raw numbers and pre-formatted JIDs
    let cleanJid = to.trim().replace(/\s+/g, "").replace("+", "");
    if (!cleanJid.endsWith("@s.whatsapp.net") && !cleanJid.includes("@")) {
      cleanJid = `${cleanJid}@s.whatsapp.net`;
    }

    const payload: QueueMessage = {
      sessionId: this.sessionId,
      to: cleanJid,
      text,
      simulateTyping: options.simulateTyping ?? true
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
    try {
      const jid = payload.to;
      const text = payload.text;

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

      await this.socket.sendMessage(jid, { text });
      console.log(`[AntiBanQueue - ${this.sessionId}] Safe dispatch succeeded to ${jid}`);
    } catch (err: any) {
      console.error(`[AntiBanQueue - ${this.sessionId}] Failed safe dispatch:`, err.message);
    }
  }

  public async disconnect() {
    if (this.redisClient && this.redisClient.isOpen) {
      await this.redisClient.disconnect();
    }
  }
}
