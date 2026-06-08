'use client';

import React, { useEffect, useState, useRef, useCallback } from 'react';

interface MessagePayload {
  id: string;
  sender: 'agent' | 'customer';
  text: string;
  timestamp: Date;
  status: 'sending' | 'sent' | 'failed';
}

interface SocketMessagePacket {
  action: 'send_override_message';
  payload: {
    tenant_id: string;
    jid: string;
    text: string;
  };
}

interface LiveChatProps {
  agentId: string;
  currentTenantId: string;
  currentConversationJid: string;
}

export default function LiveChat({ agentId, currentTenantId, currentConversationJid }: LiveChatProps) {
  const [messages, setMessages] = useState<MessagePayload[]>([]);
  const [inputText, setInputText] = useState<string>('');
  const [status, setStatus] = useState<'disconnected' | 'connecting' | 'connected'>('disconnected');
  const [sendError, setSendError] = useState<string>('');
  const [isSending, setIsSending] = useState<boolean>(false);
  
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const maxReconnectAttempts = 5;
  const reconnectAttemptsRef = useRef<number>(0);

  const connectWebSocket = useCallback(() => {
    if (wsRef.current && (wsRef.current.readyState === WebSocket.CONNECTING || wsRef.current.readyState === WebSocket.OPEN)) {
      return;
    }

    setStatus('connecting');
    setSendError('');

    const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // Mapping route accurately to backend endpoint /api/v1/ws/agent/{agentId}
    const wsUrl = `${wsProto}//${window.location.host}/api/v1/ws/agent/${agentId}`;
    console.log('[LiveChat Component] Connecting websocket to:', wsUrl);

    try {
      const socket = new WebSocket(wsUrl);
      wsRef.current = socket;

      socket.onopen = () => {
        console.log('[LiveChat Component] Websocket connection established.');
        setStatus('connected');
        reconnectAttemptsRef.current = 0;
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current);
          reconnectTimeoutRef.current = null;
        }
      };

      socket.onmessage = (event: MessageEvent) => {
        try {
          const payload = JSON.parse(event.data);
          console.log('[LiveChat Component] Event packet received:', payload);
          
          if (payload.type === 'message' && payload.data) {
            const data = payload.data;
            setMessages((prev) => {
              const exists = prev.some((m) => m.id === data.id);
              if (exists) {
                return prev.map((m) => m.id === data.id ? { ...m, status: 'sent' as const } : m);
              }
              return [
                ...prev,
                {
                  id: data.id,
                  sender: data.direction === 'inbound' ? 'customer' : 'agent',
                  text: data.content,
                  timestamp: new Date(data.created_at || Date.now()),
                  status: 'sent' as const
                }
              ];
            });
          }
        } catch (err) {
          console.error('[LiveChat Component] Failed parsing socket message data:', err);
        }
      };

      socket.onclose = (event: CloseEvent) => {
        console.warn(`[LiveChat Component] Websocket connection closed: code=${event.code}, reason=${event.reason}`);
        setStatus('disconnected');
        handleReconnection();
      };

      socket.onerror = (error: Event) => {
        console.error('[LiveChat Component] Websocket connection error:', error);
        setSendError('WebSocket connection error. Attempting to reconnect...');
      };
    } catch (err: any) {
      console.error('[LiveChat Component] Websocket setup exception:', err);
      setStatus('disconnected');
      handleReconnection();
    }
  }, [agentId]);

  const handleReconnection = useCallback(() => {
    if (reconnectAttemptsRef.current >= maxReconnectAttempts) {
      console.warn('[LiveChat Component] Max reconnection attempts exceeded.');
      setSendError('Connection lost permanently. Please refresh page to retry.');
      return;
    }

    if (reconnectTimeoutRef.current) return;

    reconnectAttemptsRef.current += 1;
    const backoffDelay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 10000);
    console.log(`[LiveChat Component] Scheduling reconnect attempt ${reconnectAttemptsRef.current} in ${backoffDelay}ms`);

    reconnectTimeoutRef.current = setTimeout(() => {
      reconnectTimeoutRef.current = null;
      connectWebSocket();
    }, backoffDelay);
  }, [connectWebSocket]);

  useEffect(() => {
    connectWebSocket();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [agentId, connectWebSocket]);

  const handleSendMessage = () => {
    const socket = wsRef.current;
    
    // Prevent duplicate sends and input validation
    if (isSending || !inputText.trim()) return;
    
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setSendError('Unable to send. Chat connection is currently disconnected.');
      return;
    }

    const targetText = inputText.trim();
    setIsSending(true);
    setSendError('');

    // Generate optimistic ID to reconcile UI state
    const optimisticId = `optimistic-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

    // Create optimistic message details
    const optimisticMessage: MessagePayload = {
      id: optimisticId,
      sender: 'agent',
      text: targetText,
      timestamp: new Date(),
      status: 'sending'
    };

    // 1. Instant optimistic rendering (Message appears locally before server acknowledgment)
    setMessages((prev) => [...prev, optimisticMessage]);
    setInputText('');

    try {
      const messagePayload: SocketMessagePacket = {
        action: 'send_override_message',
        payload: {
          jid: currentConversationJid,
          text: targetText,
          tenant_id: currentTenantId
        }
      };

      // 2. Emit structural JSON packet directly across the socket interface
      socket.send(JSON.stringify(messagePayload));

      // Mark the optimistic message as sent after successful transmit trigger
      setTimeout(() => {
        setMessages((prev) =>
          prev.map((m) => (m.id === optimisticId ? { ...m, status: 'sent' as const } : m))
        );
        setIsSending(false);
      }, 500);
    } catch (err: any) {
      console.error('[LiveChat Component] Send message error:', err);
      setSendError('Failed to route manual override message over WebSocket.');
      // Mark optimistic message as failed
      setMessages((prev) =>
        prev.map((m) => (m.id === optimisticId ? { ...m, status: 'failed' as const } : m))
      );
      setIsSending(false);
      setInputText(targetText); // Restore input value for retry
    }
  };

  return (
    <div className="flex flex-col h-full bg-slate-900 border border-slate-800 rounded-lg overflow-hidden shadow-2xl">
      <div className="flex items-center justify-between px-4 py-3 bg-slate-800 border-b border-slate-700">
        <div className="flex items-center gap-2">
          <span className="relative flex h-3 w-3">
            <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
              status === 'connected' ? 'bg-green-400' : 'bg-red-400'
            }`}></span>
            <span className={`relative inline-flex rounded-full h-3 w-3 ${
              status === 'connected' ? 'bg-green-500' : 'bg-red-500'
            }`}></span>
          </span>
          <h3 className="text-sm font-semibold text-slate-200">
            Live Chat (Manual Override Session)
          </h3>
        </div>
        <span className="text-xs text-slate-400 capitalize">{status}</span>
      </div>

      <div className="flex-1 p-4 overflow-y-auto space-y-4 min-h-[300px]">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-slate-500 text-sm space-y-1">
            <p>No override messages sent in this session.</p>
            <p className="text-xs text-slate-600">Type a message below to override the AI and send via WhatsApp.</p>
          </div>
        ) : (
          messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex flex-col max-w-[80%] rounded-lg p-3 ${
                msg.sender === 'agent'
                  ? 'bg-emerald-600 text-slate-100 ml-auto'
                  : 'bg-slate-700 text-slate-200 mr-auto'
              }`}
            >
              <div className="text-[10px] text-slate-300 font-medium mb-1 capitalize">{msg.sender}</div>
              <p className="text-sm">{msg.text}</p>
              <div className="flex items-center justify-end gap-1 mt-1">
                <span className="text-[9px] text-slate-300">{msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                {msg.sender === 'agent' && (
                  <span className="text-[9px] text-slate-200">
                    {msg.status === 'sending' && '⏳'}
                    {msg.status === 'sent' && '✓'}
                    {msg.status === 'failed' && '❌'}
                  </span>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {sendError && (
        <div className="px-4 py-2 bg-red-950/40 border-t border-red-900/30 text-xs text-red-300">
          {sendError}
        </div>
      )}

      <div className="p-3 bg-slate-850 border-t border-slate-750 flex gap-2">
        <input
          type="text"
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          placeholder={status === 'connected' ? 'Type WhatsApp message...' : 'Reconnecting to socket...'}
          disabled={status !== 'connected'}
          className="flex-1 px-4 py-2 bg-slate-800 border border-slate-700 rounded-md text-sm text-slate-200 focus:outline-none focus:border-emerald-500 transition-colors disabled:opacity-50"
          onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
        />
        <button
          onClick={handleSendMessage}
          disabled={status !== 'connected' || !inputText.trim() || isSending}
          className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-800 disabled:text-slate-600 text-white text-sm font-medium rounded-md transition-colors"
        >
          {isSending ? 'Sending...' : 'Send Override'}
        </button>
      </div>
    </div>
  );
}
