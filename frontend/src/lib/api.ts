const BASE_URL = typeof window !== 'undefined' 
  ? `${window.location.origin}/api/v1` 
  : 'http://backend:8000/api/v1';

class ApiClient {
  private getToken(): string | null {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('saas_token');
    }
    return null;
  }

  public setSession(token: string, tenantId: string, role: string) {
    if (typeof window !== 'undefined') {
      localStorage.setItem('saas_token', token);
      localStorage.setItem('saas_tenant_id', tenantId);
      localStorage.setItem('saas_role', role);
    }
  }

  public logout() {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('saas_token');
      localStorage.removeItem('saas_tenant_id');
      localStorage.removeItem('saas_role');
      window.location.href = '/login';
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
    delete: (id: string) => this.request(`/bots/${id}`, { method: 'DELETE' })
  };

  // 4. Conversation logs & Live Chat override
  public chats = {
    list: () => this.request('/chats/'),
    getMessages: (id: string) => this.request(`/chats/${id}/messages`),
    sendMessage: (payload: { session_id: string; to_phone: string; content: string }) => 
      this.request('/chats/send', { method: 'POST', body: JSON.stringify(payload) })
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
}

export const api = new ApiClient();
