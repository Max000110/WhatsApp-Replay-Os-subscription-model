'use client';

import React, { useEffect, useState, useRef } from 'react';

interface LiveChatProps {
  agentId: string;
  tenantId: string;
  customerJid: string;
}

export default function LiveChat({ agentId, tenantId, customerJid }: LiveChatProps) {
  const [messages, setMessages] = useState<Array<{ sender: string; text: string; time: string }>>([]);
  const [inputText, setInputText] = useState('');
  const [status, setStatus] = useState<'disconnected' | 'connecting' | 'connected'>('disconnected');
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    setStatus('connecting');
    const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // Connect to the newly established agent websocket endpoint
    const wsUrl = `${wsProto}//${window.location.host}/api/v1/ws/agent/${agentId}`;
    console.log('[LiveChat Component] Connecting to:', wsUrl);
    
    const socket = new WebSocket(wsUrl);
    wsRef.current = socket;

    socket.onopen = () => {
      console.log('[LiveChat Component] Connected');
      setStatus('connected');
    };

    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        console.log('[LiveChat Component] Message received:', message);
      } catch (err) {
        console.error('[LiveChat Component] Parse error:', err);
      }
    };

    socket.onclose = () => {
      console.log('[LiveChat Component] Closed');
      setStatus('disconnected');
    };

    return () => {
      socket.close();
    };
  }, [agentId]);

  const sendOverrideMessage = () => {
    if (!inputText.trim() || !wsRef.current || status !== 'connected') return;

    const payload = {
      action: 'send_override_message',
      payload: {
        jid: customerJid,
        text: inputText,
        tenant_id: tenantId,
      },
    };

    wsRef.current.send(JSON.stringify(payload));
    setMessages((prev) => [
      ...prev,
      { sender: 'Agent (You)', text: inputText, time: new Date().toLocaleTimeString() },
    ]);
    setInputText('');
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
            <p className="text-xs">Type a message below to override the AI and send via WhatsApp.</p>
          </div>
        ) : (
          messages.map((msg, index) => (
            <div
              key={index}
              className={`flex flex-col max-w-[80%] rounded-lg p-3 ${
                msg.sender.includes('You')
                  ? 'bg-emerald-600 text-slate-100 ml-auto'
                  : 'bg-slate-700 text-slate-200 mr-auto'
              }`}
            >
              <div className="text-[10px] text-slate-300 font-medium mb-1">{msg.sender}</div>
              <p className="text-sm">{msg.text}</p>
              <div className="text-[9px] text-slate-300 text-right mt-1">{msg.time}</div>
            </div>
          ))
        )}
      </div>

      <div className="p-3 bg-slate-850 border-t border-slate-750 flex gap-2">
        <input
          type="text"
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          placeholder="Type WhatsApp message..."
          className="flex-1 px-4 py-2 bg-slate-850 border border-slate-700 rounded-md text-sm text-slate-200 focus:outline-none focus:border-emerald-500 transition-colors"
          onKeyDown={(e) => e.key === 'Enter' && sendOverrideMessage()}
        />
        <button
          onClick={sendOverrideMessage}
          disabled={status !== 'connected' || !inputText.trim()}
          className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-800 disabled:text-slate-600 text-white text-sm font-medium rounded-md transition-colors"
        >
          Send Override
        </button>
      </div>
    </div>
  );
}
