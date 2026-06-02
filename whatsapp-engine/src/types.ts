export interface SessionAuth {
  creds: any;
  keys: { [key: string]: any };
}

export interface WebhookPayload {
  sessionId: string;
  phone: string | null;
  event: 'qr' | 'connected' | 'disconnected' | 'message';
  data: {
    qr?: string;
    messageId?: string;
    from?: string;
    pushName?: string;
    body?: string;
    mediaUrl?: string;
    mediaType?: string;
    timestamp?: number;
    error?: string;
  };
}

export interface QueueMessage {
  sessionId: string;
  to: string;
  text: string;
  simulateTyping?: boolean;
  messageId?: string;
  options?: {
    replyDelay?: number;
    simulateTypingDelay?: number;
    sendMode?: string;
  };
}

