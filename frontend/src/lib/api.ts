const BASE_URL = typeof window !== 'undefined' 
  ? `${window.location.origin}/api/v1` 
  : 'http://backend:8000/api/v1';

class ApiClient {
  private getToken(): string | null {
    if (typeof window !== 'undefined') {
      if (window.location.pathname.startsWith('/admin')) {
        return localStorage.getItem('replyos_admin_token');
      }
      return localStorage.getItem('saas_token');
    }
    return null;
  }

  public setSession(token: string, tenantId: string, role: string) {
    if (typeof window !== 'undefined') {
      if (window.location.pathname.startsWith('/admin')) {
        localStorage.setItem('replyos_admin_token', token);
        localStorage.setItem('replyos_admin_tenant_id', tenantId);
        localStorage.setItem('replyos_admin_role', role);
      } else {
        localStorage.setItem('saas_token', token);
        localStorage.setItem('saas_tenant_id', tenantId);
        localStorage.setItem('saas_role', role);
      }
    }
  }

  public logout() {
    if (typeof window !== 'undefined') {
      if (window.location.pathname.startsWith('/admin')) {
        localStorage.removeItem('replyos_admin_token');
        localStorage.removeItem('replyos_admin_tenant_id');
        localStorage.removeItem('replyos_admin_role');
        window.location.href = '/admin/login';
      } else {
        localStorage.removeItem('saas_token');
        localStorage.removeItem('saas_tenant_id');
        localStorage.removeItem('saas_role');
        window.location.href = '/login';
      }
    }
  }

  private async request(endpoint: string, options: RequestInit = {}) {
    const token = this.getToken();
    const headers = new Headers(options.headers || {});
    
    if (token) {
      headers.set('Authorization', `Bearer ${token}`);
    }
    
    if (!(options.body instanceof FormData) && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }

    const config = {
      ...options,
      headers
    };

    const response = await fetch(`${BASE_URL}${endpoint}`, config);
    
    if (response.status === 401) {
      this.logout();
      throw new Error('Authentication expired.');
    }

    if (!response.ok) {
      let errMsg = 'Network request failed.';
      try {
        const errData = await response.json();
        errMsg = errData.detail || errData.message || errMsg;
      } catch (e) {
        try {
          const rawText = await response.text();
          errMsg = rawText.length < 200 ? rawText : `Server Error (Status ${response.status})`;
        } catch (textErr) {
          errMsg = `Server Error (Status ${response.status})`;
        }
      }
      throw new Error(errMsg);
    }

    return response.json();
  }

  // 1. Auth endpoints
  public auth = {
    login: (payload: any) => this.request('/auth/login', { method: 'POST', body: JSON.stringify(payload) }),
    register: (payload: any) => this.request('/auth/register', { method: 'POST', body: JSON.stringify(payload) })
  };

  // 2. WhatsApp sessions
  public sessions = {
    list: () => this.request('/sessions/'),
    create: (payload: any) => this.request('/sessions/', { method: 'POST', body: JSON.stringify(payload) }),
    get: (id: string) => this.request(`/sessions/${id}`),
    delete: (id: string) => this.request(`/sessions/${id}`, { method: 'DELETE' })
  };

  // 3. AI Chatbots
  public bots = {
    list: () => this.request('/bots/'),
    create: (payload: any) => this.request('/bots/', { method: 'POST', body: JSON.stringify(payload) }),
    patch: (id: string, payload: any) => this.request(`/bots/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
    delete: (id: string) => this.request(`/bots/${id}`, { method: 'DELETE' }),
    testPrompt: (id: string, payload: { test_question: string; conversation_id?: string | null }) =>
      this.request(`/bots/${id}/test-prompt`, { method: 'POST', body: JSON.stringify(payload) })
  };

  // 4. Conversation logs & Live Chat override
  public chats = {
    list: () => this.request('/chats/'),
    getMessages: (id: string) => this.request(`/chats/${id}/messages`),
    sendMessage: (payload: { session_id: string; to_phone: string; content: string; client_uuid?: string }) => 
      this.request('/chats/send', { method: 'POST', body: JSON.stringify(payload) }),
    delete: (id: string, deleteType: string = 'soft') => 
      this.request(`/chats/${id}?delete_type=${deleteType}`, { method: 'DELETE' }),
    bulkDelete: (payload: { conversation_ids: string[]; delete_type: string }) =>
      this.request('/chats/bulk-delete', { method: 'POST', body: JSON.stringify(payload) }),
    merge: (payload: { source_conversation_ids: string[]; target_jid: string }) =>
      this.request('/chats/merge', { method: 'POST', body: JSON.stringify(payload) }),
    handoff: (id: string, payload: { status: string }) =>
      this.request(`/chats/${id}/handoff`, { method: 'POST', body: JSON.stringify(payload) }),
    release: (id: string) =>
      this.request(`/chats/${id}/release`, { method: 'POST' }),
    getContext: (id: string) =>
      this.request(`/chats/${id}/context`)
  };

  // Support Agents & Departments
  public agents = {
    list: () => this.request('/agents'),
    create: (payload: { name: string; email: string; department: string; skills?: string; status?: string }) => 
      this.request('/agents', { method: 'POST', body: JSON.stringify(payload) }),
    assign: (payload: { conversation_id: string; agent_id: string }) => 
      this.request('/agents/assign', { method: 'POST', body: JSON.stringify(payload) }),
    transfer: (payload: { conversation_id: string; target_agent_id?: string; target_department?: string }) => 
      this.request('/agents/transfer', { method: 'POST', body: JSON.stringify(payload) }),
    close: (payload: { conversation_id: string }) => 
      this.request('/agents/close', { method: 'POST', body: JSON.stringify(payload) }),
    reopen: (payload: { conversation_id: string }) => 
      this.request('/agents/reopen', { method: 'POST', body: JSON.stringify(payload) })
  };

  // Google Calendar Booking Sync
  public bookings = {
    getSlots: (date: string) => this.request(`/bookings/slots?date=${date}`),
    create: (payload: { customer_email: string; customer_phone: string; booking_date: string; booking_time: string }) => 
      this.request('/bookings', { method: 'POST', body: JSON.stringify(payload) })
  };

  // 5. RAG Document Ingestion Catalog
  public knowledge = {
    list: () => this.request('/knowledge/'),
    create: (payload: any) => this.request('/knowledge/', { method: 'POST', body: JSON.stringify(payload) }),
    getDocs: (kbId: string) => this.request(`/knowledge/${kbId}/documents`),
    uploadDoc: (kbId: string, file: File) => {
      const fd = new FormData();
      fd.append('file', file);
      return this.request(`/knowledge/${kbId}/documents`, {
        method: 'POST',
        body: fd
      });
    }
  };

  // 6. Marketing broadcast scheduling
  public campaigns = {
    list: () => this.request('/campaigns/'),
    create: (payload: any) => this.request('/campaigns/', { method: 'POST', body: JSON.stringify(payload) })
  };

  // 7. Billing & Subscriptions
  public billing = {
    getPlan: () => this.request('/billing/plan'),
    createOrder: (payload: { plan_tier: string }) => this.request('/billing/create-order', { method: 'POST', body: JSON.stringify(payload) }),
    verifyPayment: (payload: { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string; plan_tier: string }) => 
      this.request('/billing/verify-payment', { method: 'POST', body: JSON.stringify(payload) })
  };

  // 8. Admin Panel (Super Admin)
  public admin = {
    login: (payload: any) => this.request('/admin/auth/login', { method: 'POST', body: JSON.stringify(payload) }),
    changePassword: (payload: any) => this.request('/admin/auth/password-change', { method: 'POST', body: JSON.stringify(payload) }),
    totpSetup: () => this.request('/admin/auth/totp/setup', { method: 'POST' }),
    totpEnable: (payload: any) => this.request('/admin/auth/totp/enable', { method: 'POST', body: JSON.stringify(payload) }),
    totpVerify: (payload: any) => this.request('/admin/auth/totp/verify', { method: 'POST', body: JSON.stringify(payload) }),
    totpDisable: () => this.request('/admin/auth/totp/disable', { method: 'POST' }),
    changeUsername: (payload: any) => this.request('/admin/auth/change-username', { method: 'POST', body: JSON.stringify(payload) }),
    revokeSession: () => this.request('/admin/auth/revoke-session', { method: 'POST' }),
    
    getTenants: () => this.request('/admin/tenants'),
    activateTenant: (tenantId: string) => this.request(`/admin/tenants/${tenantId}/activate`, { method: 'POST' }),
    suspendTenant: (tenantId: string) => this.request(`/admin/tenants/${tenantId}/suspend`, { method: 'POST' }),
    reactivateTenant: (tenantId: string) => this.request(`/admin/tenants/${tenantId}/reactivate`, { method: 'POST' }),
    deleteTenant: (tenantId: string) => this.request(`/admin/tenants/${tenantId}`, { method: 'DELETE' }),
    changePlan: (tenantId: string, payload: { plan_tier: string; max_bots?: number; max_messages?: number; days?: number }) => 
      this.request(`/admin/tenants/${tenantId}/change-plan`, { method: 'POST', body: JSON.stringify(payload) }),
    overrideQuotas: (tenantId: string, payload: { max_bots: number; max_messages: number }) => 
      this.request(`/admin/tenants/${tenantId}/quotas`, { method: 'POST', body: JSON.stringify(payload) }),
    resetUsage: (tenantId: string) => this.request(`/admin/tenants/${tenantId}/reset-usage`, { method: 'POST' }),
    impersonate: (tenantId: string) => this.request(`/admin/tenants/${tenantId}/impersonate`, { method: 'POST' }),
    emergencyShutdown: (tenantId: string) => this.request(`/admin/tenants/${tenantId}/shutdown`, { method: 'POST' }),
    
    terminateTenant: (tenantId: string, payload: { mode: string }) => 
      this.request(`/admin/tenants/${tenantId}/terminate`, { method: 'POST', body: JSON.stringify(payload) }),
    setRetentionPolicy: (tenantId: string, payload: { policy: string }) => 
      this.request(`/admin/tenants/${tenantId}/retention-policy`, { method: 'POST', body: JSON.stringify(payload) }),
    purgeTenant: (tenantId: string) => 
      this.request(`/admin/tenants/${tenantId}/purge`, { method: 'DELETE' }),
    revokeSessions: (tenantId: string) => 
      this.request(`/admin/tenants/${tenantId}/revoke-sessions`, { method: 'POST' }),
    forceLogout: (tenantId: string) => 
      this.request(`/admin/tenants/${tenantId}/force-logout`, { method: 'POST' }),
    grantAccess: (tenantId: string) => this.request(`/admin/tenants/${tenantId}/grant-access`, { method: 'POST' }),
    revokeAccess: (tenantId: string) => this.request(`/admin/tenants/${tenantId}/revoke-access`, { method: 'POST' }),
    getStorageReport: () => this.request('/admin/storage-report'),
    emergencyLock: () => this.request('/admin/system/emergency-lock', { method: 'POST' }),
    emergencyUnlock: () => this.request('/admin/system/emergency-unlock', { method: 'POST' }),
      
    getPayments: () => this.request('/admin/payments'),
    getUsage: () => this.request('/admin/usage'),
    getSystemHealth: () => this.request('/admin/system-health'),
    getMonitoring: () => this.request('/admin/monitoring'),
    broadcastMaintenance: (message: string) => this.request('/admin/broadcast-maintenance', { method: 'POST', body: JSON.stringify({ message }) }),
    
    getAuditLogs: (limit?: number, offset?: number) => 
      this.request(`/admin/audit-logs?limit=${limit || 100}&offset=${offset || 0}`),
    getSecurityCenter: () => this.request('/admin/security-center'),
    triggerCron: () => this.request('/admin/system/trigger-cron', { method: 'POST' })
  };

  // 9. User Settings
  public settings = {
    getProfile: () => this.request('/settings/profile'),
    updateProfile: (payload: { first_name?: string; last_name?: string; email?: string }) => 
      this.request('/settings/profile', { method: 'PATCH', body: JSON.stringify(payload) }),
    changePassword: (payload: { current_password: string; new_password: string }) => 
      this.request('/settings/change-password', { method: 'POST', body: JSON.stringify(payload) }),
    getSessions: () => this.request('/settings/sessions'),
    getActivityLog: () => this.request('/settings/activity-log'),
    deleteAccount: () => this.request('/settings/account', { method: 'DELETE' }),
    getDeliveryPerformance: () => this.request('/settings/delivery-performance'),
    updateDeliveryPerformance: (payload: any) => 
      this.request('/settings/delivery-performance', { method: 'PATCH', body: JSON.stringify(payload) })
  };
}

export const api = new ApiClient();
