'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '@/lib/api';
import { 
  QrCode, Bot, MessageSquare, Megaphone, FileText, LogOut, Plus, Trash2, 
  Send, User, Clock, ShieldCheck, Database, RefreshCw, Smartphone, CheckCircle, AlertCircle, Loader2,
  Activity
} from 'lucide-react';

type Tab = 'sessions' | 'bots' | 'chats' | 'campaigns' | 'knowledge' | 'billing';

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState<Tab>('sessions');
  const [tenantName, setTenantName] = useState('Workspace Console');
  
  // Dynamic Global Refresh states
  const [sessions, setSessions] = useState<any[]>([]);
  const [bots, setBots] = useState<any[]>([]);
  const [conversations, setConversations] = useState<any[]>([]);
  const [messages, setMessages] = useState<any[]>([]);
  const [kbs, setKbs] = useState<any[]>([]);
  const [kbDocs, setKbDocs] = useState<any[]>([]);
  const [campaigns, setCampaigns] = useState<any[]>([]);
  
  // Subscription & Billing states
  const [currentPlan, setCurrentPlan] = useState<any | null>(null);
  const [showMockPaymentModal, setShowMockPaymentModal] = useState(false);
  const [mockOrderDetails, setMockOrderDetails] = useState<any | null>(null);
  const [isVerifyingPayment, setIsVerifyingPayment] = useState(false);
  
  // Selection states
  const [activeSession, setActiveSession] = useState<any | null>(null);
  const [activeConv, setActiveConv] = useState<any | null>(null);
  const [activeKb, setActiveKb] = useState<any | null>(null);

  // Form input variables
  const [newSessionName, setNewSessionName] = useState('');
  const [newBotName, setNewBotName] = useState('');
  const [newBotPrompt, setNewBotPrompt] = useState('You are an elegant customer assistant. Answer questions politely based on facts.');
  const [newBotSessionId, setNewBotSessionId] = useState('');
  const [newBotRagEnabled, setNewBotRagEnabled] = useState(false);
  const [newBotPersonality, setNewBotPersonality] = useState('Friendly');
  const [newBotModel, setNewBotModel] = useState('qwen2.5:1.5b-instruct');
  const [newBotCompanyName, setNewBotCompanyName] = useState('');
  const [newBotServices, setNewBotServices] = useState('');
  const [newBotProducts, setNewBotProducts] = useState('');
  const [newBotPricing, setNewBotPricing] = useState('');
  const [newBotPolicies, setNewBotPolicies] = useState('');
  const [newBotLocation, setNewBotLocation] = useState('');
  const [newBotWorkingHours, setNewBotWorkingHours] = useState('');
  const [newBotContactDetails, setNewBotContactDetails] = useState('');
  const [newBotCustomInstructions, setNewBotCustomInstructions] = useState('');
  const [newBotMemoryEnabled, setNewBotMemoryEnabled] = useState(false);

  // Edit bot config and sandbox states
  const [editingBot, setEditingBot] = useState<any | null>(null);
  const [sandboxQuestion, setSandboxQuestion] = useState('');
  const [sandboxResponse, setSandboxResponse] = useState<any | null>(null);
  const [sandboxLoading, setSandboxLoading] = useState(false);
  const [sandboxTab, setSandboxTab] = useState<'identity' | 'profile' | 'memory' | 'sandbox'>('identity');
  const [agentMsgText, setAgentMsgText] = useState('');
  const [newKbName, setNewKbName] = useState('');
  const [newKbDesc, setNewKbDesc] = useState('');
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [campaignName, setCampaignName] = useState('');
  const [campaignText, setCampaignText] = useState('');
  const [campaignSessionId, setCampaignSessionId] = useState('');
  const [campaignRecipients, setCampaignRecipients] = useState('');

  // Support Agent state variables
  const [agents, setAgents] = useState<any[]>([]);
  const [showAddAgentModal, setShowAddAgentModal] = useState(false);
  const [newAgentName, setNewAgentName] = useState('');
  const [newAgentEmail, setNewAgentEmail] = useState('');
  const [newAgentDept, setNewAgentDept] = useState('Support');
  const [newAgentSkills, setNewAgentSkills] = useState('');

  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState('');

  // Live Override send states
  const [isSending, setIsSending] = useState(false);
  const [sendError, setSendError] = useState('');

  // Refs for stale-closure-free access inside polling intervals
  const activeConvRef = useRef<any>(null);
  const activeKbRef = useRef<any>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Keep refs in sync with state
  useEffect(() => { activeConvRef.current = activeConv; }, [activeConv]);
  useEffect(() => { activeKbRef.current = activeKb; }, [activeKb]);

  // Auto-scroll to the latest message whenever the messages list changes
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  useEffect(() => {
    // Parse query parameters for Google OAuth callback redirects
    if (typeof window !== 'undefined') {
      const urlParams = new URLSearchParams(window.location.search);
      const queryToken = urlParams.get('token');
      const queryTenantId = urlParams.get('tenant_id');
      const queryRole = urlParams.get('role');
      
      if (queryToken) {
        localStorage.setItem('saas_token', queryToken);
        if (queryTenantId) localStorage.setItem('saas_tenant_id', queryTenantId);
        if (queryRole) localStorage.setItem('saas_role', queryRole);
        // Strip query params from browser URL bar
        window.history.replaceState({}, document.title, window.location.pathname);
      }
    }

    const token = localStorage.getItem('saas_token');
    if (!token) {
      window.location.href = '/login';
      return;
    }
    
    // Fetch initial data
    fetchDashboardCoreData();
  }, []);

  // True Realtime WebSocket Synchronization (No more polling!)
  useEffect(() => {
    const token = localStorage.getItem('saas_token');
    if (!token) return;

    let socket: any = null;
    let reconnectTimeout: any = null;
    let reconnectAttempts = 0;

    const connectWebSocket = () => {
      if (socket) {
        try { socket.close(); } catch {}
      }

      const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${wsProto}//${window.location.host}/api/v1/ws?token=${token}`;
      console.log('[WebSocket] Connecting to:', wsUrl);

      socket = new WebSocket(wsUrl);

      socket.onopen = () => {
        console.log('[WebSocket] Connected successfully.');
        reconnectAttempts = 0;
        // Core sync on connection
        fetchDashboardCoreData();
      };

      socket.onmessage = (event: any) => {
        try {
          const payload = JSON.parse(event.data);
          const { type, data } = payload;
          console.log('[WebSocket] Event received:', type, data);

          if (type === 'message') {
            if (activeConvRef.current && activeConvRef.current.id === data.conversation_id) {
              setMessages((prev) => {
                const map = new Map<string, any>();
                prev.forEach((m) => map.set(String(m.id), m));
                
                // Deduplicate/replace optimistic message matching content and direction
                let replaced = false;
                for (const [key, value] of map.entries()) {
                  if (key.startsWith('optimistic-') && value.content === data.content && value.direction === data.direction) {
                    map.delete(key);
                    map.set(String(data.id), data);
                    replaced = true;
                    break;
                  }
                }
                
                if (!replaced) {
                  map.set(String(data.id), data);
                }
                
                return Array.from(map.values()).sort(
                  (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
                );
              });
            }

            setConversations((prev) => {
              const exists = prev.some((c) => c.id === data.conversation_id);
              let list = [...prev];
              if (exists) {
                list = list.map((c) => {
                  if (c.id === data.conversation_id) {
                    return { ...c, last_message_at: data.created_at };
                  }
                  return c;
                });
              } else {
                // If it's a new conversation, we trigger a core sync to retrieve full details
                fetchDashboardCoreData();
              }
              return list.sort(
                (a, b) => new Date(b.last_message_at).getTime() - new Date(a.last_message_at).getTime()
              );
            });
          }

          else if (type === 'message_status') {
            if (activeConvRef.current && activeConvRef.current.id === data.conversation_id) {
              setMessages((prev) =>
                prev.map((m) => (m.id === data.id ? { ...m, status: data.status } : m))
              );
            }
          }

          else if (type === 'session') {
            setSessions((prev) =>
              prev.map((s) => (s.id === data.id ? { ...s, status: data.status, qr_code: data.qr_code, phone_number: data.phone_number } : s))
            );
            setActiveSession((prev: any) => {
              if (prev && prev.id === data.id) {
                return { ...prev, status: data.status, qr_code: data.qr_code, phone_number: data.phone_number };
              }
              return prev;
            });
          }

          else if (type === 'campaign') {
            setCampaigns((prev) =>
              prev.map((c) => (c.id === data.id ? { ...c, status: data.status } : c))
            );
          }

          else if (type === 'campaign_status') {
            const { campaign: freshCampaign } = data;
            setCampaigns((prev) =>
              prev.map((c) => (c.id === freshCampaign.id ? { ...c, status: freshCampaign.status } : c))
            );
          }

          else if (type === 'kb_document') {
            setKbDocs((prev) =>
              prev.map((doc) => (doc.id === data.id ? { ...doc, status: data.status } : doc))
            );
          }

        } catch (err) {
          console.error('[WebSocket] Failed parsing event:', err);
        }
      };

      socket.onclose = (e: any) => {
        console.warn('[WebSocket] Closed. Reconnecting...', e.code, e.reason);
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
        reconnectAttempts++;
        reconnectTimeout = setTimeout(() => {
          connectWebSocket();
        }, delay);
      };

      socket.onerror = (err: any) => {
        console.error('[WebSocket] Error:', err);
      };
    };

    connectWebSocket();

    return () => {
      if (socket) {
        socket.onclose = null;
        socket.close();
      }
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
    };
  }, []);

  const fetchDashboardCoreData = useCallback(async () => {
    try {
      const sessList = await api.sessions.list();
      setSessions(sessList);

      // Preserve active QR focus if updated in backend — use ref to avoid stale closure
      setActiveSession((prev: any) => {
        if (prev) {
          const found = sessList.find((s: any) => s.id === prev.id);
          return found || prev;
        }
        return prev;
      });

      const botList = await api.bots.list();
      setBots(botList);

      const convList = await api.chats.list();
      setConversations(convList);

      try {
        const agentList = await api.agents.list();
        setAgents(agentList);
      } catch (agentErr) {
        console.error('Failed fetching support agents:', agentErr);
      }

      // CRITICAL FIX: Keep activeConv in sync with fresh server data.
      if (activeConvRef.current) {
        const freshConv = convList.find((c: any) => c.id === activeConvRef.current.id);
        if (freshConv) {
          setActiveConv(freshConv);
        }
      }

      const kbList = await api.knowledge.list();
      setKbs(kbList);
      
      // Auto focus first KB if none selected — use ref to avoid stale closure
      if (kbList.length > 0 && !activeKbRef.current) {
        setActiveKb(kbList[0]);
      }

      const campaignList = await api.campaigns.list();
      setCampaigns(campaignList);

      try {
        const planInfo = await api.billing.getPlan();
        setCurrentPlan(planInfo);
      } catch (billingErr) {
        console.error('Failed fetching subscription plan:', billingErr);
      }
    } catch (err: any) {
      console.error('Core sync failed:', err.message);
    }
  }, []);

  // Sync historical messages for focused live override conversation
  useEffect(() => {
    if (activeConv) {
      const convId = activeConv.id;
      const fetchHistory = async () => {
        try {
          const msgList = await api.chats.getMessages(convId);
          setMessages((prev) => {
            const map = new Map<string, any>();
            // Keep existing optimistic bubbles
            prev.forEach((m) => {
              if (String(m.id).startsWith('optimistic-')) {
                map.set(String(m.id), m);
              }
            });
            // Overwrite/add fetched messages
            msgList.forEach((m: any) => {
              // Deduplicate/replace optimistic message matching content and direction
              let replaced = false;
              for (const [key, value] of map.entries()) {
                if (key.startsWith('optimistic-') && value.content === m.content && value.direction === m.direction) {
                  map.delete(key);
                  map.set(String(m.id), m);
                  replaced = true;
                  break;
                }
              }
              if (!replaced) {
                map.set(String(m.id), m);
              }
            });
            return Array.from(map.values()).sort(
              (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
            );
          });
        } catch (err: any) {
          console.error('Chat history fetch failed:', err.message);
        }
      };
      
      fetchHistory();
    } else {
      setMessages([]);
      setSendError('');
    }
  }, [activeConv?.id]);

  // Sync uploaded files under selected KB catalog
  useEffect(() => {
    if (activeKb) {
      const fetchKbDocs = async () => {
        try {
          const docList = await api.knowledge.getDocs(activeKb.id);
          setKbDocs(docList);
        } catch (err) {
          console.error(err);
        }
      };
      fetchKbDocs();
    } else {
      setKbDocs([]);
    }
  }, [activeKb]);

  const handleCreateSession = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSessionName.trim()) return;
    setActionLoading(true);
    setError('');
    try {
      const res = await api.sessions.create({ session_name: newSessionName });
      setSessions([...sessions, res]);
      setActiveSession(res); // Focus scanner console
      setNewSessionName('');
    } catch (err: any) {
      setError(err.message || 'Session creation failed.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteSession = async (id: string) => {
    if (!confirm('Are you sure you want to remove this session? This wipes creds.')) return;
    try {
      await api.sessions.delete(id);
      setSessions(sessions.filter(s => s.id !== id));
      if (activeSession?.id === id) setActiveSession(null);
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleCreateBot = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newBotName.trim()) return;
    setActionLoading(true);
    try {
      const res = await api.bots.create({
        name: newBotName,
        system_prompt: newBotPrompt,
        session_id: newBotSessionId || undefined,
        rag_enabled: newBotRagEnabled,
        personality: newBotPersonality,
        model_name: newBotModel,
        company_name: newBotCompanyName || undefined,
        services: newBotServices || undefined,
        products: newBotProducts || undefined,
        pricing: newBotPricing || undefined,
        policies: newBotPolicies || undefined,
        location: newBotLocation || undefined,
        working_hours: newBotWorkingHours || undefined,
        contact_details: newBotContactDetails || undefined,
        custom_instructions: newBotCustomInstructions || undefined,
        memory_enabled: newBotMemoryEnabled
      });
      setBots([...bots, res]);
      setNewBotName('');
      setNewBotPrompt('You are an elegant customer assistant. Answer questions politely based on facts.');
      setNewBotCompanyName('');
      setNewBotServices('');
      setNewBotProducts('');
      setNewBotPricing('');
      setNewBotPolicies('');
      setNewBotLocation('');
      setNewBotWorkingHours('');
      setNewBotContactDetails('');
      setNewBotCustomInstructions('');
      setNewBotMemoryEnabled(false);
    } catch (err: any) {
      alert(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleUpdateBotStatus = async (id: string, active: boolean) => {
    try {
      const res = await api.bots.patch(id, { is_active: active });
      setBots(bots.map(b => b.id === id ? res : b));
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleCreateAgentSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newAgentName.trim() || !newAgentEmail.trim()) return;
    setActionLoading(true);
    try {
      const res = await api.agents.create({
        name: newAgentName,
        email: newAgentEmail,
        department: newAgentDept,
        skills: newAgentSkills || undefined,
        status: 'online'
      });
      setAgents([...agents, res]);
      setShowAddAgentModal(false);
      setNewAgentName('');
      setNewAgentEmail('');
      setNewAgentSkills('');
    } catch (err: any) {
      alert(err.message || 'Failed to register agent.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleTakeOverHandoff = async () => {
    if (!activeConv) return;
    setActionLoading(true);
    try {
      const res = await api.chats.handoff(activeConv.id, { status: 'HUMAN_ACTIVE' });
      setActiveConv(res);
      setConversations(conversations.map(c => c.id === activeConv.id ? res : c));
    } catch (err: any) {
      alert(err.message || 'Handoff takeover failed.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleReleaseHandoff = async () => {
    if (!activeConv) return;
    setActionLoading(true);
    try {
      const res = await api.chats.release(activeConv.id);
      setActiveConv(res);
      setConversations(conversations.map(c => c.id === activeConv.id ? res : c));
    } catch (err: any) {
      alert(err.message || 'Handoff release failed.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleAssignAgentSubmit = async (agentId: string) => {
    if (!activeConv) return;
    setActionLoading(true);
    try {
      const res = await api.agents.assign({ conversation_id: activeConv.id, agent_id: agentId });
      setActiveConv(res);
      setConversations(conversations.map(c => c.id === activeConv.id ? res : c));
    } catch (err: any) {
      alert(err.message || 'Agent assignment failed.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleTransferAgentSubmit = async (targetDept: string, targetAgentId?: string) => {
    if (!activeConv) return;
    setActionLoading(true);
    try {
      const res = await api.agents.transfer({
        conversation_id: activeConv.id,
        target_agent_id: targetAgentId || undefined,
        target_department: targetDept
      });
      setActiveConv(res);
      setConversations(conversations.map(c => c.id === activeConv.id ? res : c));
    } catch (err: any) {
      alert(err.message || 'Transfer failed.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleCloseConversationSubmit = async () => {
    if (!activeConv) return;
    setActionLoading(true);
    try {
      const res = await api.agents.close({ conversation_id: activeConv.id });
      setActiveConv(res);
      setConversations(conversations.map(c => c.id === activeConv.id ? res : c));
    } catch (err: any) {
      alert(err.message || 'Failed to close conversation.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleSendAgentMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!agentMsgText.trim() || !activeConv || isSending) return;

    const txt = agentMsgText.trim();
    const conv = activeConv; // capture stable ref at call time

    setSendError('');
    setIsSending(true);

    // ── Optimistic render: show the message immediately in the thread ──
    const generateUUID = () => {
      if (typeof window !== 'undefined' && window.crypto && window.crypto.randomUUID) {
        return window.crypto.randomUUID();
      }
      return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0,
          v = c == 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
      });
    };

    const clientUuid = generateUUID();
    const optimisticId = clientUuid;
    const optimisticMsg = {
      id: optimisticId,
      conversation_id: conv.id,
      direction: 'outbound',
      sender_type: 'user',
      content: txt,
      media_url: null,
      media_type: null,
      status: 'sending',
      created_at: new Date().toISOString(),
    };
    // Clear input and add optimistic bubble using functional update (stale-free)
    setAgentMsgText('');
    setMessages((prev: any[]) => [...prev, optimisticMsg]);

    try {
      const res = await api.chats.sendMessage({
        session_id: conv.session_id,
        to_phone: conv.customer_phone,
        content: txt,
        client_uuid: clientUuid
      });

      // Replace optimistic bubble with real server response (has real id + status)
      setMessages((prev: any[]) =>
        prev.map((m: any) => (m.id === optimisticId ? res : m))
      );
    } catch (err: any) {
      // Remove optimistic bubble on failure and restore input text
      setMessages((prev: any[]) => prev.filter((m: any) => m.id !== optimisticId));
      setAgentMsgText(txt); // Give the user their text back
      setSendError(err.message || 'Failed to send message. Please try again.');
      console.error('[LiveOverride] Send failed:', err);
    } finally {
      setIsSending(false);
    }
  };

  const handleCreateKb = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newKbName.trim()) return;
    try {
      const res = await api.knowledge.create({ name: newKbName, description: newKbDesc });
      setKbs([...kbs, res]);
      setActiveKb(res);
      setNewKbName('');
      setNewKbDesc('');
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleFileUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile || !activeKb) return;
    setActionLoading(true);
    try {
      const res = await api.knowledge.uploadDoc(activeKb.id, uploadFile);
      setKbDocs([...kbDocs, res]);
      setUploadFile(null);
      // Reset input element
      const fileInput = document.getElementById('kb-file-input') as HTMLInputElement;
      if (fileInput) fileInput.value = '';
    } catch (err: any) {
      alert(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleCreateCampaign = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!campaignName || !campaignText || !campaignSessionId || !campaignRecipients) return;
    setActionLoading(true);
    try {
      const cleanList = campaignRecipients.split('\n').filter(p => p.trim().length > 0);
      const res = await api.campaigns.create({
        name: campaignName,
        template_text: campaignText,
        session_id: campaignSessionId,
        scheduled_time: new Date().toISOString(),
        recipient_phones: cleanList
      });
      setCampaigns([...campaigns, res]);
      setCampaignName('');
      setCampaignText('');
      setCampaignRecipients('');
    } catch (err: any) {
      alert(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // Load Razorpay Checkout script dynamically
  useEffect(() => {
    const script = document.createElement('script');
    script.src = 'https://checkout.razorpay.com/v1/checkout.js';
    script.async = true;
    document.body.appendChild(script);
    return () => {
      try {
        document.body.removeChild(script);
      } catch {}
    };
  }, []);

  const handleUpgradePlan = async (tier: string) => {
    setActionLoading(true);
    setError('');
    try {
      const order = await api.billing.createOrder({ plan_tier: tier });
      if (order.is_mock) {
        setMockOrderDetails({ ...order, plan_tier: tier });
        setShowMockPaymentModal(true);
      } else {
        const options = {
          key: order.razorpay_key_id,
          amount: order.amount,
          currency: order.currency,
          name: "ReplyOS",
          description: `Upgrade to ${tier.toUpperCase()}`,
          order_id: order.razorpay_order_id,
          handler: async function (response: any) {
            setActionLoading(true);
            try {
              const res = await api.billing.verifyPayment({
                razorpay_order_id: response.razorpay_order_id,
                razorpay_payment_id: response.razorpay_payment_id,
                razorpay_signature: response.razorpay_signature,
                plan_tier: tier
              });
              setCurrentPlan(res);
              alert(`Successfully upgraded to ${tier.toUpperCase()} plan!`);
            } catch (err: any) {
              alert(`Payment verification failed: ${err.message}`);
            } finally {
              setActionLoading(false);
            }
          },
          prefill: {
            name: tenantName,
            email: "billing@replyos.com"
          },
          theme: {
            color: "#6366f1"
          }
        };
        const rzp = new (window as any).Razorpay(options);
        rzp.open();
      }
    } catch (err: any) {
      alert(`Failed to initiate upgrade: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleSimulatePayment = async () => {
    if (!mockOrderDetails) return;
    setIsVerifyingPayment(true);
    try {
      const res = await api.billing.verifyPayment({
        razorpay_order_id: mockOrderDetails.razorpay_order_id,
        razorpay_payment_id: `pay_mock_${Math.random().toString(36).substring(7)}`,
        razorpay_signature: `sig_mock_${Math.random().toString(36).substring(7)}`,
        plan_tier: mockOrderDetails.plan_tier
      });
      setCurrentPlan(res);
      setShowMockPaymentModal(false);
      setMockOrderDetails(null);
      alert(`[Sandbox Success] Upgraded to ${mockOrderDetails.plan_tier.toUpperCase()} plan successfully!`);
    } catch (err: any) {
      alert(`Simulation verification failed: ${err.message}`);
    } finally {
      setIsVerifyingPayment(false);
    }
  };

  return (
    <div className="flex h-screen bg-background relative overflow-hidden text-slate-100">
      
      {/* Dynamic glow circles */}
      <div className="absolute top-[-20%] left-[-10%] w-[60%] h-[60%] bg-primary/10 rounded-full blur-[180px] pointer-events-none"></div>
      
      {/* 1. BRAND SIDEBAR */}
      <aside className="w-64 bg-card/40 backdrop-blur-xl border-r border-white/5 flex flex-col shrink-0 relative">
        <div className="p-6 border-b border-white/5 flex items-center gap-3">
          <div className="h-8 w-8 rounded-lg bg-gradient-to-tr from-primary to-violet-500 flex items-center justify-center shadow-md shadow-primary/20">
            <Smartphone className="h-4.5 w-4.5 text-white" />
          </div>
          <div>
            <h1 className="font-bold text-sm text-white leading-none">ReplyOS</h1>
            <span className="text-[10px] text-slate-400 font-semibold tracking-widest uppercase">Admin Panel</span>
          </div>
        </div>

        {/* Tab Navigator */}
        <nav className="flex-1 px-4 py-6 space-y-1.5">
          <button
            onClick={() => setActiveTab('sessions')}
            className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-semibold transition ${
              activeTab === 'sessions' 
                ? 'bg-primary text-white shadow-md shadow-primary/15' 
                : 'text-slate-400 hover:bg-white/5 hover:text-white'
            }`}
          >
            <QrCode className="h-4.5 w-4.5" />
            WA Sessions
          </button>
          
          <button
            onClick={() => setActiveTab('bots')}
            className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-semibold transition ${
              activeTab === 'bots' 
                ? 'bg-primary text-white shadow-md shadow-primary/15' 
                : 'text-slate-400 hover:bg-white/5 hover:text-white'
            }`}
          >
            <Bot className="h-4.5 w-4.5" />
            AI Bot Config
          </button>
          
          <button
            onClick={() => setActiveTab('chats')}
            className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-semibold transition ${
              activeTab === 'chats' 
                ? 'bg-primary text-white shadow-md shadow-primary/15' 
                : 'text-slate-400 hover:bg-white/5 hover:text-white'
            }`}
          >
            <MessageSquare className="h-4.5 w-4.5" />
            Live Override
          </button>

          <button
            onClick={() => setActiveTab('campaigns')}
            className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-semibold transition ${
              activeTab === 'campaigns' 
                ? 'bg-primary text-white shadow-md shadow-primary/15' 
                : 'text-slate-400 hover:bg-white/5 hover:text-white'
            }`}
          >
            <Megaphone className="h-4.5 w-4.5" />
            Campaigns
          </button>

          <button
            onClick={() => setActiveTab('knowledge')}
            className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-semibold transition ${
              activeTab === 'knowledge' 
                ? 'bg-primary text-white shadow-md shadow-primary/15' 
                : 'text-slate-400 hover:bg-white/5 hover:text-white'
            }`}
          >
            <FileText className="h-4.5 w-4.5" />
            RAG Documents
          </button>

          <button
            onClick={() => setActiveTab('billing')}
            className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-semibold transition ${
              activeTab === 'billing' 
                ? 'bg-primary text-white shadow-md shadow-primary/15' 
                : 'text-slate-400 hover:bg-white/5 hover:text-white'
            }`}
          >
            <ShieldCheck className="h-4.5 w-4.5" />
            Subscription & Plans
          </button>
        </nav>

        {/* Footer Admin Zone */}
        <div className="p-4 border-t border-white/5 flex items-center justify-between gap-2.5">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-full bg-slate-800 flex items-center justify-center">
              <User className="h-4 w-4 text-slate-400" />
            </div>
            <div className="text-xs truncate max-w-[120px]">
              <p className="font-semibold text-slate-200">Tenant Space</p>
              <p className="text-[10px] text-slate-500 capitalize">{currentPlan?.plan_tier || 'Free'} Account</p>
            </div>
          </div>
          <button 
            onClick={() => api.logout()} 
            className="p-1.5 hover:bg-red-500/10 text-slate-400 hover:text-red-400 rounded-lg transition"
            title="Sign out of Console"
          >
            <LogOut className="h-4.5 w-4.5" />
          </button>
        </div>
      </aside>

      {/* 2. DYNAMIC WORKSPACE PANEL */}
      <main className="flex-1 flex flex-col bg-slate-950/40 relative overflow-hidden">
        
        {/* Workspace Top Header Bar */}
        <header className="h-16 border-b border-white/5 px-8 flex items-center justify-between backdrop-blur-md">
          <h2 className="font-bold text-lg text-white capitalize flex items-center gap-2">
            {activeTab === 'sessions' && <><QrCode className="h-5 w-5 text-primary" /> WhatsApp Web Sessions</>}
            {activeTab === 'bots' && <><Bot className="h-5 w-5 text-primary" /> Bot Orchestrator</>}
            {activeTab === 'chats' && <><MessageSquare className="h-5 w-5 text-primary" /> Customer Inbox & Live Override</>}
            {activeTab === 'campaigns' && <><Megaphone className="h-5 w-5 text-primary" /> Marketing Broadcast campaigns</>}
            {activeTab === 'knowledge' && <><Database className="h-5 w-5 text-primary" /> RAG Knowledge Store</>}
            {activeTab === 'billing' && <><ShieldCheck className="h-5 w-5 text-primary" /> Subscription & Plans</>}
          </h2>
          <div className="flex items-center gap-2 text-xs text-slate-400 bg-white/5 py-1.5 px-3 rounded-full border border-white/5">
            <span className="h-2 w-2 rounded-full bg-accent animate-pulse"></span>
            CPU Node: Stable
          </div>
        </header>

        {/* Outer body wrapper */}
        <div className="flex-1 p-8 overflow-y-auto">
          
          {/* ======================================= */}
          {/* TAB 1: WHATSAPP WEB CONNECTOR */}
          {/* ======================================= */}
          {activeTab === 'sessions' && (
            <div className="grid grid-cols-3 gap-8 items-start">
              
              {/* Left pane: Create & List sessions */}
              <div className="col-span-2 space-y-6">
                
                <div className="bg-card border border-white/5 p-6 rounded-xl shadow-lg relative">
                  <h3 className="text-sm font-semibold text-slate-200 mb-4 flex items-center gap-2">
                    <Plus className="h-4.5 w-4.5 text-primary" /> Mount New WhatsApp Web Instance
                  </h3>
                  <form onSubmit={handleCreateSession} className="flex gap-4">
                    <input
                      type="text"
                      value={newSessionName}
                      onChange={(e) => setNewSessionName(e.target.value)}
                      placeholder="e.g. Sales Account, Support Line"
                      className="flex-1 bg-slate-950/50 border border-white/5 rounded-lg py-2 px-4 text-sm focus:outline-none focus:border-primary/50"
                      required
                    />
                    <button
                      type="submit"
                      disabled={actionLoading}
                      className="bg-primary hover:bg-primary-hover px-5 rounded-lg font-semibold text-sm transition text-white disabled:opacity-50"
                    >
                      Provision Session
                    </button>
                  </form>
                </div>

                <div className="bg-card border border-white/5 p-6 rounded-xl shadow-lg">
                  <h3 className="text-sm font-semibold text-slate-200 mb-4">Active Connection Instances</h3>
                  {sessions.length === 0 ? (
                    <div className="text-center py-10 border border-dashed border-white/5 rounded-xl">
                      <Smartphone className="h-8 w-8 text-slate-600 mx-auto mb-2" />
                      <p className="text-slate-400 text-xs">No active WhatsApp connections configured yet.</p>
                    </div>
                  ) : (
                    <div className="divide-y divide-white/5">
                      {sessions.map((s: any) => (
                        <div key={s.id} className="py-4 flex items-center justify-between first:pt-0 last:pb-0">
                          <div>
                            <p className="font-semibold text-sm text-slate-200">{s.session_name}</p>
                            <div className="flex items-center gap-3 mt-1">
                              <span className={`text-[10px] uppercase font-semibold px-2 py-0.5 rounded-full ${
                                s.status === 'connected' ? 'bg-accent/10 text-accent border border-accent/20' :
                                s.status === 'scanning' ? 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20' :
                                'bg-slate-800 text-slate-400'
                              }`}>
                                {s.status}
                              </span>
                              {s.phone_number && <span className="text-[10px] text-slate-500 font-medium">JID: {s.phone_number}</span>}
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            {s.status !== 'connected' && (
                              <button
                                onClick={() => setActiveSession(s)}
                                className="text-xs bg-slate-800 hover:bg-slate-700 px-3 py-1.5 rounded-lg font-semibold text-slate-200 transition"
                              >
                                View QR
                              </button>
                            )}
                            <button
                              onClick={() => handleDeleteSession(s.id)}
                              className="p-1.5 bg-red-950/20 text-slate-500 hover:text-red-400 rounded-lg border border-transparent hover:border-red-500/10 transition"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

              </div>

              {/* Right pane: Interactive QR screen viewer */}
              <div className="bg-card border border-white/5 p-6 rounded-xl shadow-lg flex flex-col items-center">
                <h3 className="text-sm font-semibold text-slate-200 mb-6 text-center w-full pb-3 border-b border-white/5">
                  Link Account (QR Terminal Stream)
                </h3>
                {activeSession ? (
                  <div className="flex flex-col items-center text-center">
                    <p className="text-xs text-slate-400 mb-4 uppercase tracking-wider font-semibold">Instance: {activeSession.session_name}</p>
                    
                    {activeSession.status === 'scanning' && activeSession.qr_code ? (
                      <div className="bg-white p-4 rounded-xl shadow-inner border border-white/10 flex items-center justify-center">
                        {/* Stream actual QR back from Baileys */}
                        <img 
                          src={`https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(activeSession.qr_code)}`} 
                          alt="Scan QR Connection Link" 
                          className="h-48 w-48"
                        />
                      </div>
                    ) : activeSession.status === 'connected' ? (
                      <div className="flex flex-col items-center py-6">
                        <CheckCircle className="h-12 w-12 text-accent mb-3" />
                        <p className="text-sm font-bold text-slate-200">Device linked successfully!</p>
                        <p className="text-xs text-slate-500 mt-1">Ready to automate responses.</p>
                      </div>
                    ) : (
                      <div className="flex flex-col items-center py-8">
                        <RefreshCw className="h-8 w-8 text-slate-600 animate-spin mb-3" />
                        <p className="text-xs text-slate-400">Loading system state socket thread...</p>
                      </div>
                    )}
                    
                    <p className="text-[10px] text-slate-500 mt-6 max-w-[200px]">
                      Open WhatsApp on your phone, go to Linked Devices, and scan this QR code to authenticate.
                    </p>
                  </div>
                ) : (
                  <div className="py-20 text-center">
                    <Smartphone className="h-10 w-10 text-slate-700 mx-auto mb-3" />
                    <p className="text-xs text-slate-400">Select an initializing session on the left to show the QR camera feed.</p>
                  </div>
                )}
              </div>

            </div>
          )}

          {/* ======================================= */}
          {/* TAB 2: AI BOT CONFIGURATOR */}
          {/* ======================================= */}
          {activeTab === 'bots' && (
            <div className="grid grid-cols-3 gap-8 items-start">
              
              {/* Form creation */}
              <div className="bg-card border border-white/5 p-6 rounded-xl shadow-lg space-y-4">
                <h3 className="text-sm font-semibold text-slate-200 pb-3 border-b border-white/5 flex items-center gap-2">
                  <Plus className="h-4.5 w-4.5 text-primary" /> Create New AI Assistant
                </h3>
                <form onSubmit={handleCreateBot} className="space-y-4">
                  <div>
                    <label className="block text-xs text-slate-400 font-semibold mb-1">Bot Name</label>
                    <input
                      type="text"
                      value={newBotName}
                      onChange={(e) => setNewBotName(e.target.value)}
                      placeholder="e.g. Sales Closer, FAQ Bot"
                      className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2 px-3.5 text-sm focus:outline-none focus:border-primary/50"
                      required
                    />
                  </div>

                  <div>
                    <label className="block text-xs text-slate-400 font-semibold mb-1">Attach to WhatsApp account</label>
                    <select
                      value={newBotSessionId}
                      onChange={(e) => setNewBotSessionId(e.target.value)}
                      className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2 px-3.5 text-sm text-slate-300 focus:outline-none focus:border-primary/50"
                      required
                    >
                      <option value="">-- Choose Connected Line --</option>
                      {sessions.filter(s => s.status === 'connected').map(s => (
                        <option key={s.id} value={s.id}>{s.session_name} ({s.phone_number})</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs text-slate-400 font-semibold mb-1">RAG Context vectoring</label>
                    <div className="flex items-center gap-2 mt-1 bg-slate-950/40 p-2.5 rounded-lg border border-white/5">
                      <input
                        type="checkbox"
                        id="rag_checkbox"
                        checked={newBotRagEnabled}
                        onChange={(e) => setNewBotRagEnabled(e.target.checked)}
                        className="rounded border-white/5 bg-slate-900 text-primary focus:ring-primary/20 h-4 w-4"
                      />
                      <label htmlFor="rag_checkbox" className="text-xs text-slate-300 font-medium">Inject Knowledge Base retrieval</label>
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs text-slate-400 font-semibold mb-1">System Instructions</label>
                    <textarea
                      value={newBotPrompt}
                      onChange={(e) => setNewBotPrompt(e.target.value)}
                      rows={5}
                      className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2 px-3.5 text-xs focus:outline-none focus:border-primary/50 leading-relaxed"
                      required
                    />
                  </div>

                  <button
                    type="submit"
                    disabled={actionLoading}
                    className="w-full bg-primary hover:bg-primary-hover text-white py-2.5 rounded-lg text-sm font-semibold transition mt-2"
                  >
                    Deploy Chatbot
                  </button>
                </form>
              </div>

              {/* Bot Catalog */}
              <div className="col-span-2 space-y-6">
                <div className="bg-card border border-white/5 p-6 rounded-xl shadow-lg">
                  <h3 className="text-sm font-semibold text-slate-200 mb-4">Active Chatbots</h3>
                  {bots.length === 0 ? (
                    <div className="text-center py-12 border border-dashed border-white/5 rounded-xl">
                      <Bot className="h-8 w-8 text-slate-600 mx-auto mb-2" />
                      <p className="text-slate-400 text-xs">No active chatbots configured yet.</p>
                    </div>
                  ) : (
                    <div className="grid grid-cols-2 gap-6">
                      {bots.map((b: any) => (
                        <div key={b.id} className="p-4 bg-slate-950/30 border border-white/5 rounded-xl flex flex-col justify-between">
                          <div>
                            <div className="flex items-center justify-between mb-2">
                              <h4 className="font-bold text-sm text-slate-200">{b.name}</h4>
                              <span className={`text-[9px] font-semibold px-2 py-0.5 rounded-full ${
                                b.is_active ? 'bg-accent/10 text-accent border border-accent/20' : 'bg-slate-800 text-slate-400'
                              }`}>
                                {b.is_active ? 'Active' : 'Offline'}
                              </span>
                            </div>
                            
                            <p className="text-[10px] text-slate-400 font-semibold tracking-wider uppercase">Instructions:</p>
                            <p className="text-[11px] text-slate-400 line-clamp-3 mt-1 leading-relaxed bg-slate-950/60 p-2 rounded border border-white/5 mb-3">
                              {b.system_prompt}
                            </p>

                            <div className="flex flex-col gap-1.5 text-[10px] text-slate-500 mb-4 font-semibold uppercase tracking-wider">
                              <p className="flex items-center gap-1.5"><Smartphone className="h-3 w-3" /> Attached: {sessions.find(s => s.id === b.session_id)?.session_name || 'Global Unbound'}</p>
                              <p className="flex items-center gap-1.5"><Database className="h-3 w-3" /> RAG Search: {b.rag_enabled ? 'Enabled' : 'Disabled'}</p>
                            </div>
                          </div>

                          <div className="flex items-center gap-2 border-t border-white/5 pt-3 mt-2">
                            <button
                              onClick={() => handleUpdateBotStatus(b.id, !b.is_active)}
                              className={`text-[11px] px-2.5 py-1 rounded-lg font-semibold transition ${
                                b.is_active 
                                  ? 'bg-slate-800 hover:bg-slate-700 text-slate-300' 
                                  : 'bg-primary hover:bg-primary-hover text-white'
                              }`}
                            >
                              {b.is_active ? 'Deactivate' : 'Activate'}
                            </button>
                            <button
                              onClick={() => {
                                setEditingBot(b);
                                setSandboxTab('identity');
                                setSandboxQuestion('');
                                setSandboxResponse(null);
                              }}
                              className="text-[11px] bg-slate-800/80 hover:bg-slate-800 border border-white/5 px-2.5 py-1 rounded-lg text-slate-300 font-semibold transition"
                            >
                              Configure Brain
                            </button>
                            <button
                              onClick={async () => {
                                if (confirm('Delete bot?')) {
                                  await api.bots.delete(b.id);
                                  setBots(bots.filter(x => x.id !== b.id));
                                }
                              }}
                              className="text-[11px] text-red-400 hover:underline ml-auto font-semibold"
                            >
                              Delete
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

            </div>
          )}

          {/* ======================================= */}
          {/* TAB 3: LIVE AGENT CHAT OVERRIDE */}
          {/* ======================================= */}
          {activeTab === 'chats' && (
            <div className="grid grid-cols-3 gap-8 h-[calc(100vh-12rem)] items-stretch">
              
              {/* Left Column: Conversations & Support Agents Sidebar */}
              <div className="flex flex-col gap-6 h-[calc(100vh-12rem)] overflow-hidden">
                
                {/* Conversations Section */}
                <div className="flex-[3] bg-card border border-white/5 rounded-xl shadow-lg flex flex-col overflow-hidden">
                  <h3 className="text-sm font-semibold text-slate-200 p-4 border-b border-white/5 shrink-0">Conversations</h3>
                  <div className="flex-1 overflow-y-auto p-3 space-y-2">
                    {conversations.length === 0 ? (
                      <div className="text-center py-10">
                        <MessageSquare className="h-6 w-6 text-slate-700 mx-auto mb-2" />
                        <p className="text-[11px] text-slate-500">No message channels found.</p>
                      </div>
                    ) : (
                      conversations.map((c: any) => (
                        <button
                          key={c.id}
                          onClick={() => setActiveConv(c)}
                          className={`w-full text-left p-3 rounded-lg border transition ${
                            activeConv?.id === c.id 
                              ? 'bg-primary/10 border-primary/30 text-white' 
                              : 'bg-slate-950/20 border-white/5 text-slate-400 hover:bg-white/5 hover:text-white'
                          }`}
                        >
                          <p className="font-bold text-xs text-slate-200">{c.customer_name || 'Guest User'}</p>
                          <p className="text-[10px] text-slate-500 font-semibold tracking-wide mt-0.5">Phone: +{c.customer_phone}</p>
                          <p className="text-[9px] text-slate-600 mt-2 flex items-center gap-1.5"><Clock className="h-2.5 w-2.5" /> {new Date(c.last_message_at).toLocaleTimeString()}</p>
                        </button>
                      ))
                    )}
                  </div>
                </div>

                {/* Support Agents Section */}
                <div className="flex-[2] bg-card border border-white/5 rounded-xl shadow-lg flex flex-col overflow-hidden">
                  <div className="p-4 border-b border-white/5 shrink-0 flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-slate-200">Support Agents</h3>
                    <button
                      onClick={() => setShowAddAgentModal(true)}
                      className="text-[10px] bg-primary hover:bg-primary-hover text-white px-2 py-1 rounded font-semibold transition"
                    >
                      + Add Agent
                    </button>
                  </div>
                  <div className="flex-1 overflow-y-auto p-3 space-y-2">
                    {agents.length === 0 ? (
                      <div className="text-center py-6 text-slate-600 text-xs">
                        No support agents registered.
                      </div>
                    ) : (
                      agents.map((a: any) => (
                        <div key={a.id} className="p-2.5 bg-slate-950/30 border border-white/5 rounded-lg flex items-center justify-between text-xs">
                          <div>
                            <p className="font-semibold text-slate-200">{a.name}</p>
                            <p className="text-[10px] text-slate-500">{a.department} • {a.email}</p>
                          </div>
                          <span className={`h-2 w-2 rounded-full ${a.status === 'online' ? 'bg-emerald-500 animate-pulse' : 'bg-slate-700'}`}></span>
                        </div>
                      ))
                    )}
                  </div>
                </div>

              </div>

              {/* Right Columns: Thread & override input */}
              <div className="col-span-2 bg-card border border-white/5 rounded-xl shadow-lg flex flex-col overflow-hidden">
                {activeConv ? (
                  <>
                    {/* Thread Header */}
                    <div className="p-4 border-b border-white/5 shrink-0 flex flex-col gap-4 bg-slate-950/20">
                      <div className="flex items-center justify-between">
                        <div>
                          <h4 className="font-bold text-sm text-slate-200">{activeConv.customer_name || 'Guest User'}</h4>
                          <p className="text-[10px] text-slate-500 font-medium">JID: {activeConv.customer_phone}</p>
                        </div>
                        <div className="flex items-center gap-3">
                          {/* Dynamic Handoff Status Badge */}
                          <span className={`text-[9px] uppercase tracking-wider font-bold px-2.5 py-0.5 rounded-full flex items-center gap-1.5 border ${
                            activeConv.handoff_status === 'HUMAN_ACTIVE'
                              ? 'bg-red-500/10 text-red-400 border-red-500/20'
                              : activeConv.handoff_status === 'WAITING_AGENT'
                                ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                                : activeConv.handoff_status === 'RESOLVED'
                                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                                  : 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20'
                          }`}>
                            <span className={`h-1.5 w-1.5 rounded-full ${
                              activeConv.handoff_status === 'HUMAN_ACTIVE'
                                ? 'bg-red-400 animate-pulse'
                                : activeConv.handoff_status === 'WAITING_AGENT'
                                  ? 'bg-amber-400 animate-bounce'
                                  : activeConv.handoff_status === 'RESOLVED'
                                    ? 'bg-emerald-400'
                                    : 'bg-indigo-400'
                            }`}></span>
                            <span>{activeConv.handoff_status || 'AI_ACTIVE'}</span>
                          </span>

                          {/* Close/Resolve Button */}
                          {activeConv.handoff_status !== 'RESOLVED' && (
                            <button
                              onClick={handleCloseConversationSubmit}
                              className="text-[10px] bg-emerald-600 hover:bg-emerald-500 text-white font-semibold px-2.5 py-1 rounded transition"
                            >
                              Resolve
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Handoff State Triggers & Agent Management */}
                      <div className="flex items-center gap-4 flex-wrap border-t border-white/5 pt-3">
                        {activeConv.handoff_status === 'HUMAN_ACTIVE' ? (
                          <button
                            onClick={handleReleaseHandoff}
                            className="text-xs bg-slate-800 hover:bg-slate-750 text-slate-300 hover:text-white font-medium px-3.5 py-1.5 rounded-lg border border-white/5 transition"
                          >
                            Release back to AI
                          </button>
                        ) : (
                          <button
                            onClick={handleTakeOverHandoff}
                            className="text-xs bg-primary hover:bg-primary-hover text-white font-medium px-3.5 py-1.5 rounded-lg transition shadow-md shadow-primary/20"
                          >
                            Take Over Handoff
                          </button>
                        )}

                        {/* Assign Agent Dropdown */}
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider">Assign Agent:</span>
                          <select
                            value={activeConv.assigned_agent_id || ''}
                            onChange={(e) => {
                              if (e.target.value) handleAssignAgentSubmit(e.target.value);
                            }}
                            className="bg-slate-950 border border-white/5 rounded-lg text-xs py-1.5 px-3 focus:outline-none text-slate-300"
                          >
                            <option value="">-- Select Agent --</option>
                            {agents.map((a: any) => (
                              <option key={a.id} value={a.id}>{a.name} ({a.department})</option>
                            ))}
                          </select>
                        </div>

                        {/* Transfer Department Dropdown */}
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider">Transfer Dept:</span>
                          <select
                            value={activeConv.lead_stage || ''}
                            onChange={(e) => {
                              if (e.target.value) handleTransferAgentSubmit(e.target.value);
                            }}
                            className="bg-slate-950 border border-white/5 rounded-lg text-xs py-1.5 px-3 focus:outline-none text-slate-300"
                          >
                            <option value="">-- Select Dept --</option>
                            <option value="Support">Support</option>
                            <option value="Sales">Sales</option>
                            <option value="Billing">Billing</option>
                            <option value="Technical">Technical</option>
                          </select>
                        </div>
                      </div>
                    </div>

                    {/* Scrollable bubble container */}
                    <div className="flex-1 overflow-y-auto p-6 space-y-4 flex flex-col">
                      {messages.map((m: any) => (
                        <div 
                          key={m.id} 
                          className={`max-w-[70%] p-3.5 rounded-xl text-xs leading-relaxed transition-opacity ${
                            m.direction === 'inbound'
                              ? 'bg-slate-950/60 border border-white/5 text-slate-200 self-start'
                              : `bg-primary text-white self-end shadow-md shadow-primary/10 ${
                                  m.status === 'sending' ? 'opacity-60' : 'opacity-100'
                                }`
                          }`}
                        >
                          <p>{m.content}</p>
                          <span className={`text-[8px] uppercase tracking-widest font-semibold block mt-2 text-right ${
                            m.direction === 'inbound' ? 'text-slate-500' : 'text-primary-hover'
                          }`}>
                            {m.direction === 'inbound'
                              ? `${m.sender_type} • ${new Date(m.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}`
                              : m.status === 'sending'
                                ? '⏳ sending...'
                                : m.status === 'failed'
                                  ? '❌ failed'
                                  : `✓ ${m.sender_type} • ${new Date(m.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}`
                            }
                          </span>
                        </div>
                      ))}
                      {/* Auto-scroll anchor */}
                      <div ref={messagesEndRef} />
                    </div>

                    {/* Inline send error banner — shown INSTEAD of alert() */}
                    {sendError && (
                      <div className="mx-4 mb-1 flex items-center gap-2 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
                        <AlertCircle className="h-3.5 w-3.5 text-red-400 shrink-0" />
                        <p className="text-[11px] text-red-300 flex-1">{sendError}</p>
                        <button
                          onClick={() => setSendError('')}
                          className="text-red-400 hover:text-red-200 text-xs ml-2"
                        >✕</button>
                      </div>
                    )}

                    {/* Agent override input form */}
                    <form onSubmit={handleSendAgentMessage} className="p-4 border-t border-white/5 bg-slate-950/30 shrink-0 flex gap-4">
                      <input
                        type="text"
                        value={agentMsgText}
                        onChange={(e) => { setAgentMsgText(e.target.value); if (sendError) setSendError(''); }}
                        placeholder={isSending ? 'Sending to WhatsApp...' : 'Live agent override mode: Type reply bypassing chatbot...'}
                        className={`flex-1 bg-slate-950/60 border rounded-lg py-2.5 px-4 text-xs focus:outline-none transition ${
                          sendError
                            ? 'border-red-500/50 focus:border-red-400/70'
                            : 'border-white/5 focus:border-primary/50'
                        } ${isSending ? 'opacity-60 cursor-not-allowed' : ''}`}
                        disabled={isSending}
                      />
                      <button
                        type="submit"
                        disabled={isSending || !agentMsgText.trim()}
                        className="bg-primary hover:bg-primary-hover disabled:opacity-50 disabled:cursor-not-allowed px-5 rounded-lg flex items-center justify-center text-white transition shadow-md shadow-primary/25 min-w-[44px]"
                      >
                        {isSending
                          ? <Loader2 className="h-4 w-4 animate-spin" />
                          : <Send className="h-4 w-4" />}
                      </button>
                    </form>
                  </>
                ) : (
                  <div className="flex-1 flex flex-col items-center justify-center text-slate-500">
                    <MessageSquare className="h-10 w-10 mb-3" />
                    <p className="text-xs">Select a customer conversation thread from the sidebar to activate live agent controls.</p>
                  </div>
                )}
              </div>

            </div>
          )}

          {/* ======================================= */}
          {/* TAB 4: MARKETING CAMPAIGNS */}
          {/* ======================================= */}
          {activeTab === 'campaigns' && (
            <div className="grid grid-cols-3 gap-8 items-start">
              
              {/* Creator Card */}
              <div className="bg-card border border-white/5 p-6 rounded-xl shadow-lg space-y-4">
                <h3 className="text-sm font-semibold text-slate-200 pb-3 border-b border-white/5 flex items-center gap-2">
                  <Megaphone className="h-4.5 w-4.5 text-primary" /> Schedule Broadcast
                </h3>
                <form onSubmit={handleCreateCampaign} className="space-y-4">
                  <div>
                    <label className="block text-xs text-slate-400 font-semibold mb-1">Campaign Name</label>
                    <input
                      type="text"
                      value={campaignName}
                      onChange={(e) => setCampaignName(e.target.value)}
                      placeholder="e.g. Black Friday Launch"
                      className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2 px-3.5 text-sm focus:outline-none focus:border-primary/50"
                      required
                    />
                  </div>

                  <div>
                    <label className="block text-xs text-slate-400 font-semibold mb-1">Sender WhatsApp JID</label>
                    <select
                      value={campaignSessionId}
                      onChange={(e) => setCampaignSessionId(e.target.value)}
                      className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2 px-3.5 text-sm text-slate-300 focus:outline-none focus:border-primary/50"
                      required
                    >
                      <option value="">-- Choose Account --</option>
                      {sessions.filter(s => s.status === 'connected').map(s => (
                        <option key={s.id} value={s.id}>{s.session_name}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs text-slate-400 font-semibold mb-1">Recipient Phone JIDs (one per line)</label>
                    <textarea
                      value={campaignRecipients}
                      onChange={(e) => setCampaignRecipients(e.target.value)}
                      rows={4}
                      placeholder="919876543210&#10;917654321098"
                      className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2 px-3.5 text-xs focus:outline-none focus:border-primary/50 leading-relaxed font-mono"
                      required
                    />
                  </div>

                  <div>
                    <label className="block text-xs text-slate-400 font-semibold mb-1">Template Broadcast Body</label>
                    <textarea
                      value={campaignText}
                      onChange={(e) => setCampaignText(e.target.value)}
                      rows={5}
                      className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2 px-3.5 text-xs focus:outline-none focus:border-primary/50 leading-relaxed"
                      placeholder="Hello from Acme! Here is your exclusive offer..."
                      required
                    />
                  </div>

                  <button
                    type="submit"
                    disabled={actionLoading}
                    className="w-full bg-primary hover:bg-primary-hover text-white py-2.5 rounded-lg text-sm font-semibold transition"
                  >
                    {actionLoading ? 'Initializing logs...' : 'Dispatch Broadcast'}
                  </button>
                </form>
              </div>

              {/* History list */}
              <div className="col-span-2 space-y-6">
                <div className="bg-card border border-white/5 p-6 rounded-xl shadow-lg">
                  <h3 className="text-sm font-semibold text-slate-200 mb-4">Broadcast Analytics</h3>
                  {campaigns.length === 0 ? (
                    <div className="text-center py-12 border border-dashed border-white/5 rounded-xl">
                      <Megaphone className="h-8 w-8 text-slate-600 mx-auto mb-2" />
                      <p className="text-slate-400 text-xs">No campaign dispatches initiated yet.</p>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {campaigns.map((c: any) => (
                        <div key={c.id} className="p-4 bg-slate-950/30 border border-white/5 rounded-xl flex items-center justify-between">
                          <div>
                            <h4 className="font-bold text-sm text-slate-200">{c.name}</h4>
                            <p className="text-[11px] text-slate-500 mt-1 max-w-sm truncate">{c.template_text}</p>
                            <p className="text-[9px] text-slate-600 mt-2 font-semibold uppercase tracking-wider">Scheduled: {new Date(c.scheduled_time).toLocaleString()}</p>
                          </div>
                          <span className={`text-[10px] uppercase font-bold tracking-wider px-3 py-1 rounded-full ${
                            c.status === 'completed' ? 'bg-accent/10 text-accent border border-accent/20' :
                            c.status === 'sending' ? 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20' :
                            'bg-slate-800 text-slate-400'
                          }`}>
                            {c.status}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

            </div>
          )}

          {/* ======================================= */}
          {/* TAB 5: RAG DOCUMENT INGESTOR */}
          {/* ======================================= */}
          {activeTab === 'knowledge' && (
            <div className="grid grid-cols-3 gap-8 items-start">
              
              {/* Creator column */}
              <div className="space-y-6">
                
                <div className="bg-card border border-white/5 p-6 rounded-xl shadow-lg space-y-4">
                  <h3 className="text-sm font-semibold text-slate-200 pb-3 border-b border-white/5 flex items-center gap-2">
                    <Plus className="h-4.5 w-4.5 text-primary" /> Create Knowledge base
                  </h3>
                  <form onSubmit={handleCreateKb} className="space-y-4">
                    <div>
                      <label className="block text-xs text-slate-400 font-semibold mb-1">Catalog Name</label>
                      <input
                        type="text"
                        value={newKbName}
                        onChange={(e) => setNewKbName(e.target.value)}
                        placeholder="e.g. Sales Guidelines, FAQ Guide"
                        className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2 px-3.5 text-sm focus:outline-none focus:border-primary/50"
                        required
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 font-semibold mb-1">Short Description</label>
                      <textarea
                        value={newKbDesc}
                        onChange={(e) => setNewKbDesc(e.target.value)}
                        rows={2}
                        className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2 px-3.5 text-xs focus:outline-none focus:border-primary/50"
                      />
                    </div>
                    <button
                      type="submit"
                      className="w-full bg-primary hover:bg-primary-hover text-white py-2 rounded-lg text-sm font-semibold transition"
                    >
                      Provision Catalog
                    </button>
                  </form>
                </div>

                <div className="bg-card border border-white/5 p-6 rounded-xl shadow-lg">
                  <h3 className="text-sm font-semibold text-slate-200 mb-4">Active Catalogs</h3>
                  {kbs.length === 0 ? (
                    <p className="text-xs text-slate-500 text-center py-4">No catalogs created.</p>
                  ) : (
                    <div className="space-y-2">
                      {kbs.map(k => (
                        <button
                          key={k.id}
                          onClick={() => setActiveKb(k)}
                          className={`w-full text-left p-3 rounded-lg border transition ${
                            activeKb?.id === k.id 
                              ? 'bg-primary/10 border-primary/30 text-white' 
                              : 'bg-slate-950/20 border-white/5 text-slate-400 hover:bg-white/5 hover:text-white'
                          }`}
                        >
                          <p className="font-bold text-xs text-slate-200">{k.name}</p>
                          <p className="text-[10px] text-slate-500 mt-1 leading-relaxed truncate">{k.description || 'No description provided.'}</p>
                        </button>
                      ))}
                    </div>
                  )}
                </div>

              </div>

              {/* Uploads and chunks lists */}
              <div className="col-span-2 space-y-6">
                {activeKb ? (
                  <>
                    <div className="bg-card border border-white/5 p-6 rounded-xl shadow-lg">
                      <h3 className="text-sm font-bold text-slate-200 mb-1">Catalog: {activeKb.name}</h3>
                      <p className="text-[11px] text-slate-400 mb-4 font-semibold tracking-wider uppercase">Active Ingestion Pipeline</p>
                      
                      <form onSubmit={handleFileUpload} className="flex gap-4 p-4 bg-slate-950/40 border border-white/5 rounded-xl items-center">
                        <input
                          id="kb-file-input"
                          type="file"
                          accept=".pdf,.txt"
                          onChange={(e) => setUploadFile(e.target.files ? e.target.files[0] : null)}
                          className="flex-1 text-xs text-slate-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-primary file:text-white file:hover:bg-primary-hover file:cursor-pointer"
                          required
                        />
                        <button
                          type="submit"
                          disabled={actionLoading}
                          className="bg-primary hover:bg-primary-hover text-white text-xs font-semibold px-4 py-2 rounded-lg transition"
                        >
                          {actionLoading ? 'Splitting & Vectorizing...' : 'Upload Ingest'}
                        </button>
                      </form>
                    </div>

                    <div className="bg-card border border-white/5 p-6 rounded-xl shadow-lg">
                      <h3 className="text-sm font-semibold text-slate-200 mb-4">Ingested Document Catalog</h3>
                      {kbDocs.length === 0 ? (
                        <div className="text-center py-10 border border-dashed border-white/5 rounded-xl">
                          <FileText className="h-8 w-8 text-slate-600 mx-auto mb-2" />
                          <p className="text-slate-400 text-xs">No business files ingested yet.</p>
                        </div>
                      ) : (
                        <div className="divide-y divide-white/5">
                          {kbDocs.map((d: any) => (
                            <div key={d.id} className="py-3 flex items-center justify-between first:pt-0 last:pb-0">
                              <div>
                                <p className="font-semibold text-xs text-slate-200">{d.filename}</p>
                                <p className="text-[9px] text-slate-500 font-semibold uppercase tracking-wider mt-1">Uploaded: {new Date(d.created_at).toLocaleDateString()}</p>
                              </div>
                              <span className={`text-[9px] uppercase tracking-wider font-bold px-2 py-0.5 rounded-full ${
                                d.status === 'processed' ? 'bg-accent/10 text-accent border border-accent/20' :
                                d.status === 'processing' ? 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20' :
                                'bg-red-500/10 text-red-400'
                              }`}>
                                {d.status}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </>
                ) : (
                  <div className="bg-card border border-white/5 p-12 text-center rounded-xl shadow-lg">
                    <Database className="h-8 w-8 text-slate-600 mx-auto mb-2" />
                    <p className="text-slate-400 text-xs">Provision and select a business catalog on the left to activate RAG uploads.</p>
                  </div>
                )}
              </div>

            </div>
          )}

          {/* ======================================= */}
          {/* TAB 6: BILLING & SUBSCRIPTIONS */}
          {/* ======================================= */}
          {activeTab === 'billing' && (
            <div className="space-y-8 max-w-7xl mx-auto pb-12">
              
              {/* Current Subscription Status Panel */}
              <div className="bg-card border border-white/5 p-6 rounded-xl shadow-lg relative overflow-hidden">
                <div className="absolute top-0 right-0 w-64 h-64 bg-primary/5 rounded-full blur-[80px] pointer-events-none"></div>
                <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
                  <div>
                    <h3 className="text-lg font-bold text-white flex items-center gap-2">
                      <ShieldCheck className="h-5 w-5 text-accent" /> Active Workspace Plan
                    </h3>
                    <p className="text-xs text-slate-400 mt-1">Manage billing, subscription limits, and upgrades below.</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider">Status:</span>
                    <span className="text-xs font-bold uppercase tracking-wider px-3 py-1 bg-accent/10 text-accent border border-accent/20 rounded-full">
                      {currentPlan?.status || 'Active'}
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 mt-8 pt-6 border-t border-white/5">
                  <div className="p-4 bg-slate-950/40 border border-white/5 rounded-xl">
                    <p className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Plan Tier</p>
                    <p className="text-lg font-extrabold text-white mt-1 capitalize">{currentPlan?.plan_tier || 'Free'}</p>
                  </div>
                  <div className="p-4 bg-slate-950/40 border border-white/5 rounded-xl">
                    <p className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">WhatsApp Session Capacity</p>
                    <p className="text-lg font-extrabold text-white mt-1">
                      {sessions.filter(s => s.status === 'connected').length} / {currentPlan?.max_bots || 1} Connected
                    </p>
                  </div>
                  <div className="p-4 bg-slate-950/40 border border-white/5 rounded-xl">
                    <p className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Monthly Outbound Cap</p>
                    <p className="text-lg font-extrabold text-white mt-1">
                      {currentPlan?.max_messages_per_month || 500} messages/mo
                    </p>
                  </div>
                </div>

                {currentPlan?.current_period_end && currentPlan?.plan_tier !== 'free' && (
                  <p className="text-[10px] text-slate-500 mt-4 font-semibold">
                    Billing Cycle Ends: {new Date(currentPlan.current_period_end).toLocaleDateString()}
                  </p>
                )}
              </div>

              {/* Pricing Cards Grid */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-6 items-stretch">
                {[
                  {
                    tier: 'free',
                    price: '₹0',
                    desc: 'For small operators beginning automated scaling.',
                    maxBots: '1 Active WhatsApp session',
                    maxMsgs: '500 Outbound Messages/Month',
                    features: ['1 Chatbot Assistant', 'Basic Ollama Replies', 'Mock RAG Context', 'Community Forum support']
                  },
                  {
                    tier: 'starter',
                    price: '₹999',
                    desc: 'Ideal for small retail businesses or regional coaching centers.',
                    maxBots: '2 Active WhatsApp sessions',
                    maxMsgs: '5,000 Outbound Messages/Month',
                    features: ['Unlimited Chatbots catalog', 'Fast Ollama Inference', '2 RAG Ingest Documents', 'Email/Ticket Support']
                  },
                  {
                    tier: 'pro',
                    price: '₹2,999',
                    desc: 'Perfect for fast-growing real estate & ecommerce brands.',
                    maxBots: '5 Active WhatsApp sessions',
                    maxMsgs: '50,000 Outbound Messages/Month',
                    features: ['Campaign Analytics dashboards', 'Deep Vector Store RAG search', '50 RAG Ingest Documents', 'Priority Chat Support']
                  },
                  {
                    tier: 'agency',
                    price: '₹9,999',
                    desc: 'Built for marketing agencies managing multiple lines.',
                    maxBots: '20 Active WhatsApp sessions',
                    maxMsgs: '1,000,000 Outbound Messages/Month',
                    features: ['SaaS Tenant isolation rules', 'Dedicated API Gateway access', 'Unlimited RAG context maps', '24/7 Account SRE manager']
                  }
                ].map((plan) => {
                  const isActive = (currentPlan?.plan_tier || 'free') === plan.tier;
                  return (
                    <div 
                      key={plan.tier}
                      className={`bg-card border rounded-xl p-6 shadow-lg flex flex-col justify-between relative transition-transform hover:scale-[1.01] ${
                        isActive 
                          ? 'border-primary shadow-primary/5 ring-1 ring-primary' 
                          : 'border-white/5'
                      }`}
                    >
                      {isActive && (
                        <div className="absolute top-[-10px] left-1/2 transform -translate-x-1/2 bg-primary text-white text-[9px] uppercase font-bold tracking-widest px-3 py-1 rounded-full border border-primary/20 shadow-md">
                          Current Tier
                        </div>
                      )}
                      
                      <div>
                        <h4 className="font-extrabold text-sm capitalize text-white mb-1 flex items-center justify-between">
                          {plan.tier}
                        </h4>
                        <div className="flex items-baseline gap-1 my-4">
                          <span className="text-2xl font-black text-white">{plan.price}</span>
                          <span className="text-slate-500 text-xs font-semibold">/month</span>
                        </div>
                        <p className="text-slate-400 text-[11px] leading-relaxed mb-6">{plan.desc}</p>
                        
                        <ul className="space-y-2 border-t border-white/5 pt-4 mb-6">
                          <li className="text-[11px] font-bold text-accent flex items-center gap-1.5">
                            <span className="h-1.5 w-1.5 bg-accent rounded-full"></span> {plan.maxBots}
                          </li>
                          <li className="text-[11px] font-bold text-accent flex items-center gap-1.5">
                            <span className="h-1.5 w-1.5 bg-accent rounded-full"></span> {plan.maxMsgs}
                          </li>
                          {plan.features.map((f, i) => (
                            <li key={i} className="text-[11px] text-slate-400 flex items-center gap-1.5">
                              <span className="h-1.5 w-1.5 bg-slate-600 rounded-full"></span> {f}
                            </li>
                          ))}
                        </ul>
                      </div>

                      <button
                        onClick={() => handleUpgradePlan(plan.tier)}
                        disabled={isActive || actionLoading || plan.tier === 'free'}
                        className={`w-full py-2 rounded-lg text-xs font-bold transition ${
                          isActive 
                            ? 'bg-slate-800 text-slate-400 cursor-not-allowed border border-white/5'
                            : plan.tier === 'free'
                              ? 'bg-slate-900 text-slate-500 cursor-not-allowed border border-white/5'
                              : 'bg-primary hover:bg-primary-hover text-white shadow-md shadow-primary/10'
                        }`}
                      >
                        {isActive ? 'Current Plan' : plan.tier === 'free' ? 'Default Plan' : `Upgrade to ${plan.tier}`}
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

        </div>
      </main>

      {/* 3. MOCK PAYMENT MODAL OVERLAY */}
      {showMockPaymentModal && mockOrderDetails && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-white/10 rounded-2xl w-full max-w-md p-6 shadow-2xl relative animate-in fade-in zoom-in duration-200">
            <div className="absolute top-0 right-0 w-32 h-32 bg-primary/10 rounded-full blur-[40px] pointer-events-none"></div>
            
            <div className="flex items-center gap-3 border-b border-white/5 pb-4 mb-6">
              <div className="h-10 w-10 rounded-lg bg-yellow-500/10 flex items-center justify-center border border-yellow-500/20">
                <ShieldCheck className="h-5 w-5 text-yellow-500" />
              </div>
              <div>
                <h3 className="font-bold text-sm text-white">Razorpay Sandbox Gateway</h3>
                <p className="text-[10px] text-slate-400">Mock Order Verification Interface</p>
              </div>
            </div>

            <div className="space-y-4 bg-slate-950/40 p-4 rounded-xl border border-white/5 text-xs">
              <div className="flex justify-between">
                <span className="text-slate-500">Order ID:</span>
                <span className="font-mono text-slate-300 font-semibold">{mockOrderDetails.razorpay_order_id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Upgrade Tier:</span>
                <span className="capitalize font-bold text-accent">{mockOrderDetails.plan_tier}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Amount Due:</span>
                <span className="font-extrabold text-white">₹{(mockOrderDetails.amount / 100).toLocaleString()}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Currency:</span>
                <span className="text-slate-300 font-bold">{mockOrderDetails.currency}</span>
              </div>
            </div>

            <div className="flex flex-col gap-2 mt-6">
              <button
                onClick={handleSimulatePayment}
                disabled={isVerifyingPayment}
                className="w-full bg-primary hover:bg-primary-hover text-white py-2.5 rounded-lg text-xs font-bold transition flex items-center justify-center gap-2"
              >
                {isVerifyingPayment ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Verifying mock signature...
                  </>
                ) : (
                  'Simulate Successful Payment'
                )}
              </button>
              
              <button
                onClick={() => {
                  setShowMockPaymentModal(false);
                  setMockOrderDetails(null);
                }}
                disabled={isVerifyingPayment}
                className="w-full bg-slate-800 hover:bg-slate-700 text-slate-300 py-2.5 rounded-lg text-xs font-bold transition"
              >
                Cancel Sandbox Checkout
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Tenant AI Brain Customization Modal */}
      {editingBot && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-md p-4 overflow-y-auto">
          <div className="bg-slate-900 border border-white/10 p-6 rounded-2xl w-full max-w-4xl shadow-2xl space-y-6 my-8">
            <div className="flex justify-between items-center pb-4 border-b border-white/5">
              <div>
                <h3 className="text-base font-bold text-slate-200 flex items-center gap-2">
                  <Bot className="h-5 w-5 text-primary animate-pulse" />
                  Configure AI Brain: {editingBot.name}
                </h3>
                <p className="text-[11px] text-slate-400 mt-0.5">Customize multi-tenant isolation, personality builder, custom policies, and run sandbox prompt testing.</p>
              </div>
              <button 
                onClick={() => setEditingBot(null)} 
                className="text-slate-400 hover:text-white bg-slate-800/50 hover:bg-slate-800 rounded-full h-8 w-8 flex items-center justify-center transition"
              >
                ✕
              </button>
            </div>

            {/* Tabs selection */}
            <div className="flex gap-2 p-1 bg-slate-950/50 border border-white/5 rounded-xl">
              {[
                { id: 'identity', label: 'Identity & Style' },
                { id: 'profile', label: 'Business Profile' },
                { id: 'memory', label: 'Memory & RAG' },
                { id: 'sandbox', label: 'Testing Sandbox' }
              ].map((t) => (
                <button
                  key={t.id}
                  onClick={() => setSandboxTab(t.id as any)}
                  className={`flex-1 py-2 px-3 text-xs font-semibold rounded-lg transition ${
                    sandboxTab === t.id 
                      ? 'bg-primary text-white shadow-lg' 
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {/* TAB CONTENT */}
            <div className="space-y-4 min-h-[350px] max-h-[50vh] overflow-y-auto pr-1">
              
              {/* TAB 1: IDENTITY & STYLE */}
              {sandboxTab === 'identity' && (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs text-slate-400 font-semibold mb-1">Personality Builder Style</label>
                      <select
                        value={editingBot.personality || 'Friendly'}
                        onChange={(e) => setEditingBot({ ...editingBot, personality: e.target.value })}
                        className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2 px-3 text-xs focus:outline-none focus:border-primary/50 text-slate-200"
                      >
                        <option value="Professional">👔 Professional (Polite, structured, authoritative)</option>
                        <option value="Friendly">😊 Friendly (Warm, helpful, empathetic)</option>
                        <option value="Sales Agent">🚀 Sales Agent (Enthusiastic, benefit-focused, persuasive)</option>
                        <option value="Technical Support">🛠️ Technical Support (Analytical, step-by-step troubleshooter)</option>
                        <option value="Medical Assistant">🩺 Medical Assistant (Empathetic, clear, boundary-aware)</option>
                        <option value="Legal Assistant">⚖️ Legal Assistant (Objective, highly precise, literal)</option>
                        <option value="Custom">⚙️ Custom Tone Strategy (Uses custom prompt rules)</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 font-semibold mb-1">Active LLM Model Selection</label>
                      <select
                        value={editingBot.model_name || 'qwen2.5:1.5b-instruct'}
                        onChange={(e) => setEditingBot({ ...editingBot, model_name: e.target.value })}
                        className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2 px-3 text-xs focus:outline-none focus:border-primary/50 text-slate-200"
                      >
                        <option value="qwen2.5:1.5b-instruct">qwen2.5 (1.5B Instruct) — Fast & Reliable</option>
                        <option value="llama3:latest">llama3 (8B) — Creative & Detailed</option>
                        <option value="deepseek-coder:latest">deepseek (7B Coder) — Analytical & Precise</option>
                        <option value="mistral:latest">mistral (7B) — Conversational</option>
                        <option value="gemma2:latest">gemma2 (9B) — Structured Reasoning</option>
                      </select>
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs text-slate-400 font-semibold mb-1">Custom System Instructions / Core Prompt</label>
                    <textarea
                      value={editingBot.system_prompt}
                      onChange={(e) => setEditingBot({ ...editingBot, system_prompt: e.target.value })}
                      rows={4}
                      className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2 px-3 text-xs focus:outline-none focus:border-primary/50 text-slate-300 leading-relaxed font-mono"
                      placeholder="You are an assistant for XYZ company specializing in..."
                    />
                  </div>
                  
                  <div>
                    <label className="block text-xs text-slate-400 font-semibold mb-1">Custom Instructions (Layer 5 Override)</label>
                    <textarea
                      value={editingBot.custom_instructions || ''}
                      onChange={(e) => setEditingBot({ ...editingBot, custom_instructions: e.target.value })}
                      rows={3}
                      className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2 px-3 text-xs focus:outline-none focus:border-primary/50 text-slate-300 leading-relaxed"
                      placeholder="e.g. Always reply in Spanish. Never discuss competitors. Keep responses under 2 sentences."
                    />
                  </div>
                </div>
              )}

              {/* TAB 2: BUSINESS PROFILE */}
              {sandboxTab === 'profile' && (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs text-slate-400 font-semibold mb-1">Company/Brand Name</label>
                      <input
                        type="text"
                        value={editingBot.company_name || ''}
                        onChange={(e) => setEditingBot({ ...editingBot, company_name: e.target.value })}
                        placeholder="e.g. Quantum AI Tech"
                        className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2 px-3 text-xs focus:outline-none focus:border-primary/50 text-slate-300"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 font-semibold mb-1">Business Hours / Availability</label>
                      <input
                        type="text"
                        value={editingBot.working_hours || ''}
                        onChange={(e) => setEditingBot({ ...editingBot, working_hours: e.target.value })}
                        placeholder="e.g. Mon-Fri 9:00 AM - 6:00 PM PST"
                        className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2 px-3 text-xs focus:outline-none focus:border-primary/50 text-slate-300"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs text-slate-400 font-semibold mb-1">Services Offered</label>
                      <textarea
                        value={editingBot.services || ''}
                        onChange={(e) => setEditingBot({ ...editingBot, services: e.target.value })}
                        rows={3}
                        placeholder="e.g. AI Consulting, WhatsApp integrations..."
                        className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2 px-3 text-xs focus:outline-none focus:border-primary/50 text-slate-300 leading-relaxed"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 font-semibold mb-1">Products & Catalog</label>
                      <textarea
                        value={editingBot.products || ''}
                        onChange={(e) => setEditingBot({ ...editingBot, products: e.target.value })}
                        rows={3}
                        placeholder="e.g. ReplyOS Conversational Suite..."
                        className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2 px-3 text-xs focus:outline-none focus:border-primary/50 text-slate-300 leading-relaxed"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs text-slate-400 font-semibold mb-1">Pricing Structure</label>
                      <textarea
                        value={editingBot.pricing || ''}
                        onChange={(e) => setEditingBot({ ...editingBot, pricing: e.target.value })}
                        rows={3}
                        placeholder="e.g. Starter: $29/mo, Pro: $79/mo..."
                        className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2 px-3 text-xs focus:outline-none focus:border-primary/50 text-slate-300 leading-relaxed"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 font-semibold mb-1">Business Location / Address</label>
                      <textarea
                        value={editingBot.location || ''}
                        onChange={(e) => setEditingBot({ ...editingBot, location: e.target.value })}
                        rows={3}
                        placeholder="e.g. 123 Silicon Valley Road, CA"
                        className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2 px-3 text-xs focus:outline-none focus:border-primary/50 text-slate-300 leading-relaxed"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs text-slate-400 font-semibold mb-1">Policies (Refunds, SLAs)</label>
                      <textarea
                        value={editingBot.policies || ''}
                        onChange={(e) => setEditingBot({ ...editingBot, policies: e.target.value })}
                        rows={2}
                        placeholder="e.g. No refunds, 99.9% SLA uptime."
                        className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2 px-3 text-xs focus:outline-none focus:border-primary/50 text-slate-300 leading-relaxed"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 font-semibold mb-1">Contact Details</label>
                      <textarea
                        value={editingBot.contact_details || ''}
                        onChange={(e) => setEditingBot({ ...editingBot, contact_details: e.target.value })}
                        rows={2}
                        placeholder="e.g. email: info@acme.com, phone: +1234567"
                        className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2 px-3 text-xs focus:outline-none focus:border-primary/50 text-slate-300 leading-relaxed"
                      />
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 3: MEMORY & RAG */}
              {sandboxTab === 'memory' && (
                <div className="space-y-6">
                  <div className="bg-slate-950/40 p-4 rounded-xl border border-white/5 flex gap-4 items-start">
                    <div className="pt-0.5">
                      <input
                        type="checkbox"
                        id="memory_enabled_checkbox"
                        checked={editingBot.memory_enabled || false}
                        onChange={(e) => setEditingBot({ ...editingBot, memory_enabled: e.target.checked })}
                        className="rounded border-white/5 bg-slate-900 text-primary focus:ring-primary/20 h-4 w-4"
                      />
                    </div>
                    <div>
                      <label htmlFor="memory_enabled_checkbox" className="block text-sm font-semibold text-slate-200 mb-1 cursor-pointer">
                        Enable Customer Memory Layer (Layer 6)
                      </label>
                      <p className="text-xs text-slate-400 leading-relaxed">
                        Allows the chatbot to track customer preferences, past interactions summary, open support tickets, and lead statuses (cold/warm/hot). It will automatically inject this personalized memory context to generate context-aware replies.
                      </p>
                    </div>
                  </div>

                  <div className="bg-slate-950/40 p-4 rounded-xl border border-white/5 flex gap-4 items-start">
                    <div className="pt-0.5">
                      <input
                        type="checkbox"
                        id="rag_enabled_checkbox"
                        checked={editingBot.rag_enabled || false}
                        onChange={(e) => setEditingBot({ ...editingBot, rag_enabled: e.target.checked })}
                        className="rounded border-white/5 bg-slate-900 text-primary focus:ring-primary/20 h-4 w-4"
                      />
                    </div>
                    <div>
                      <label htmlFor="rag_enabled_checkbox" className="block text-sm font-semibold text-slate-200 mb-1 cursor-pointer">
                        Enable RAG Document Ingestion (Layer 4)
                      </label>
                      <p className="text-xs text-slate-400 leading-relaxed">
                        Enables the Vector Similarity Search pipeline using PostgreSQL pgvector. Chatbots will dynamically retrieve relevant paragraphs from your uploaded PDF/TXT/Markdown knowledge documents and inject them before submitting generation requests to the LLM.
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 4: TESTING SANDBOX */}
              {sandboxTab === 'sandbox' && (
                <div className="space-y-4">
                  <div className="bg-blue-500/10 border border-blue-500/20 p-4 rounded-xl flex gap-3 text-blue-300 leading-relaxed">
                    <Activity className="h-5 w-5 shrink-0 mt-0.5" />
                    <div>
                      <p className="text-xs font-bold uppercase tracking-wider mb-1">Prompt Testing Console</p>
                      <p className="text-[11px] text-slate-300">
                        Test your AI brain configuration in a secure sandbox. Submit queries to preview the final assembled prompt hierarchy (System, Identity, Business profile, RAG facts, Memory context), retrieved document chunks, and the resulting LLM completion in real-time.
                      </p>
                    </div>
                  </div>

                  <div className="flex gap-3">
                    <input
                      type="text"
                      value={sandboxQuestion}
                      onChange={(e) => setSandboxQuestion(e.target.value)}
                      placeholder="Ask a test question (e.g. What services do you provide? What are your hours?)"
                      className="flex-1 bg-slate-950 border border-white/10 rounded-xl py-2 px-3 text-xs focus:outline-none focus:border-primary/50 text-slate-200"
                    />
                    <button
                      onClick={async () => {
                        if (!sandboxQuestion.trim()) return;
                        setSandboxLoading(true);
                        setSandboxResponse(null);
                        try {
                          const res = await api.bots.testPrompt(editingBot.id, { test_question: sandboxQuestion });
                          setSandboxResponse(res);
                        } catch (err: any) {
                          alert(err.message || 'Testing request failed.');
                        } finally {
                          setSandboxLoading(false);
                        }
                      }}
                      disabled={sandboxLoading || !sandboxQuestion.trim()}
                      className="bg-primary hover:bg-primary-hover text-white text-xs px-5 rounded-xl font-semibold flex items-center gap-1.5 transition disabled:opacity-50"
                    >
                      {sandboxLoading && <Loader2 className="h-3 w-3 animate-spin" />}
                      Run Sandbox Query
                    </button>
                  </div>

                  {sandboxResponse && (
                    <div className="grid grid-cols-2 gap-4 pt-2">
                      <div className="space-y-2">
                        <label className="block text-[10px] text-slate-400 font-bold uppercase tracking-wider">Assembled Dynamic System Prompt</label>
                        <div className="bg-slate-950 p-4 rounded-xl border border-white/5 text-[11px] font-mono text-slate-300 h-64 overflow-y-auto whitespace-pre-wrap leading-relaxed">
                          {sandboxResponse.constructed_prompt}
                        </div>
                      </div>
                      <div className="space-y-2">
                        <label className="block text-[10px] text-slate-400 font-bold uppercase tracking-wider">Generated LLM Response & Context</label>
                        <div className="bg-slate-950 p-4 rounded-xl border border-white/5 text-[11px] h-64 overflow-y-auto flex flex-col justify-between">
                          <div className="text-slate-200 whitespace-pre-wrap leading-relaxed mb-4">
                            {sandboxResponse.llm_response}
                          </div>
                          {sandboxResponse.retrieved_context && (
                            <div className="mt-auto border-t border-white/5 pt-3">
                              <span className="block text-[9px] text-slate-500 font-bold uppercase tracking-wider mb-1">RAG Context:</span>
                              <span className="text-[10px] text-slate-400 block line-clamp-3 leading-normal font-sans">{sandboxResponse.retrieved_context}</span>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}

            </div>

            {/* MODAL FOOTER */}
            <div className="flex justify-end gap-3 pt-4 border-t border-white/5">
              <button
                onClick={() => setEditingBot(null)}
                className="px-4 py-2 rounded-xl text-xs font-semibold bg-slate-800 text-slate-400 hover:text-white transition"
              >
                Cancel
              </button>
              <button
                onClick={async () => {
                  setActionLoading(true);
                  try {
                    const res = await api.bots.patch(editingBot.id, {
                      name: editingBot.name,
                      system_prompt: editingBot.system_prompt,
                      model_name: editingBot.model_name,
                      rag_enabled: editingBot.rag_enabled,
                      personality: editingBot.personality,
                      company_name: editingBot.company_name || null,
                      services: editingBot.services || null,
                      products: editingBot.products || null,
                      pricing: editingBot.pricing || null,
                      policies: editingBot.policies || null,
                      location: editingBot.location || null,
                      working_hours: editingBot.working_hours || null,
                      contact_details: editingBot.contact_details || null,
                      custom_instructions: editingBot.custom_instructions || null,
                      memory_enabled: editingBot.memory_enabled
                    });
                    setBots(bots.map(x => x.id === editingBot.id ? res : x));
                    setEditingBot(null);
                  } catch (err: any) {
                    alert(err.message || 'Saving configuration failed.');
                  } finally {
                    setActionLoading(false);
                  }
                }}
                disabled={actionLoading}
                className="px-5 py-2 rounded-xl text-xs font-semibold bg-primary hover:bg-primary-hover text-white transition flex items-center gap-1.5 disabled:opacity-50"
              >
                {actionLoading && <Loader2 className="h-3 w-3 animate-spin" />}
                Save Brain Settings
              </button>
            </div>
          </div>
        </div>
      )}
      {/* 4. ADD SUPPORT AGENT MODAL OVERLAY */}
      {showAddAgentModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-md bg-slate-900 border border-white/5 rounded-2xl shadow-2xl p-6 relative">
            <h3 className="text-base font-bold text-white mb-4">Register New Support Agent</h3>
            <form onSubmit={handleCreateAgentSubmit} className="space-y-4">
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">Agent Name</label>
                <input
                  type="text"
                  required
                  value={newAgentName}
                  onChange={(e) => setNewAgentName(e.target.value)}
                  placeholder="Jane Support"
                  className="w-full bg-slate-950 border border-white/5 rounded-lg py-2 px-3 text-xs focus:outline-none focus:border-primary/50 text-white"
                />
              </div>

              <div>
                <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">Agent Email</label>
                <input
                  type="email"
                  required
                  value={newAgentEmail}
                  onChange={(e) => setNewAgentEmail(e.target.value)}
                  placeholder="jane@company.com"
                  className="w-full bg-slate-950 border border-white/5 rounded-lg py-2 px-3 text-xs focus:outline-none focus:border-primary/50 text-white"
                />
              </div>

              <div>
                <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">Department</label>
                <select
                  value={newAgentDept}
                  onChange={(e) => setNewAgentDept(e.target.value)}
                  className="w-full bg-slate-950 border border-white/5 rounded-lg py-2 px-3 text-xs focus:outline-none focus:border-primary/50 text-white"
                >
                  <option value="Support">Support</option>
                  <option value="Sales">Sales</option>
                  <option value="Billing">Billing</option>
                  <option value="Technical">Technical</option>
                </select>
              </div>

              <div>
                <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">Skills / Notes</label>
                <input
                  type="text"
                  value={newAgentSkills}
                  onChange={(e) => setNewAgentSkills(e.target.value)}
                  placeholder="Customer service, troubleshooting, pgvector RAG"
                  className="w-full bg-slate-950 border border-white/5 rounded-lg py-2 px-3 text-xs focus:outline-none focus:border-primary/50 text-white"
                />
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t border-white/5">
                <button
                  type="button"
                  onClick={() => setShowAddAgentModal(false)}
                  className="px-4 py-2 rounded-xl text-xs font-semibold bg-slate-800 text-slate-400 hover:text-white transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="px-5 py-2 rounded-xl text-xs font-semibold bg-primary hover:bg-primary-hover text-white transition disabled:opacity-50"
                >
                  Register Agent
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
