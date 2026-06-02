'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { 
  Activity, Shield, Coins, Users, MessageSquare, HardDrive, RefreshCw, 
  AlertTriangle, Play, LogOut, Key, Terminal, Settings, ShieldCheck, 
  ToggleLeft, ToggleRight, Trash2, UserCheck, UserX, AlertOctagon, HelpCircle
} from 'lucide-react';

const formatBytes = (bytes: number) => {
  if (!bytes) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

export default function AdminDashboardPage() {
  const router = useRouter();
  
  const isProtectedTenant = (t: any) => {
    return t.name === "System Operations" || t.subdomain === "admin";
  };
  
  // Tab Management: 'tenants' | 'observability' | 'audits' | 'security' | 'settings'
  const [activeTab, setActiveTab] = useState<'tenants' | 'observability' | 'audits' | 'security' | 'settings'>('tenants');
  
  // Data States
  const [tenants, setTenants] = useState<any[]>([]);
  const [payments, setPayments] = useState<any[]>([]);
  const [health, setHealth] = useState<any>({
    system: { cpu_percent: 0, ram_percent: 0, disk_percent: 0 },
    services: {
      postgres: 'offline',
      redis: 'offline',
      redis_latency_ms: 0,
      whatsapp_engine: 'offline',
      whatsapp_active_sessions: 0,
      ai_runtime: 'offline',
      websockets: { status: 'offline', active_tenants: 0, active_connections: 0 },
      celery_workers: { status: 'offline', queue_size: 0 }
    }
  });
  const [monitoring, setMonitoring] = useState<any>({
    delivery_failures: { failed_messages: 0, failed_campaign_logs: 0 },
    redis_queues: { whatsapp_queues: {}, celery_queue_size: 0 },
    failed_payments: { count: 0, recent: [] },
    security_violations: { banned_ips_count: 0, banned_ips: [], active_rate_limit_violations: 0 },
    websocket_health: { active_tenants: 0, active_connections: 0 }
  });
  const [usage, setUsage] = useState<any>({
    global_usage: { total_messages: 0, outbound_messages: 0, total_ai_tokens: 0, avg_ai_latency_ms: 0 },
    message_distribution: {}
  });
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [securityCenter, setSecurityCenter] = useState<any>({ metrics: {}, banned_ips: [], recent_security_events: [] });
  const [storageReport, setStorageReport] = useState<any>(null);
  
  // Interface Loading & Errors
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  
  // Modal controllers & Forms payload
  const [activeTenant, setActiveTenant] = useState<any | null>(null);
  const [modalType, setModalType] = useState<'plan' | 'quota' | 'terminate' | null>(null);
  
  // Forms states
  const [planForm, setPlanForm] = useState({ plan_tier: 'starter', max_bots: 2, max_messages: 2000, days: 30 });
  const [quotaForm, setQuotaForm] = useState({ max_bots: 2, max_messages: 2000 });
  const [terminateMode, setTerminateMode] = useState<'graceful' | 'instant'>('graceful');
  const [maintenanceMsg, setMaintenanceMsg] = useState('');
  
  // TOTP generation States
  const [totpQr, setTotpQr] = useState('');
  const [totpSecret, setTotpSecret] = useState('');
  const [totpVerifyCode, setTotpVerifyCode] = useState('');
  const [totpRecoveryCodes, setTotpRecoveryCodes] = useState<string[]>([]);
  const [totpSetupStep, setTotpSetupStep] = useState<'idle' | 'generated' | 'locked'>('idle');
  const [adminEmail, setAdminEmail] = useState('admin@replyos.com');
  const [newEmail, setNewEmail] = useState('admin@replyos.com');

  // Verify auth session on load
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const urlParams = new URLSearchParams(window.location.search);
      const queryToken = urlParams.get('token');
      if (queryToken) {
        localStorage.setItem('replyos_admin_token', queryToken);
        window.history.replaceState({}, document.title, window.location.pathname);
      }
    }

    const adminToken = localStorage.getItem('replyos_admin_token');
    if (!adminToken) {
      router.push('/admin/login');
    } else {
      fetchDashboardData();
    }
  }, []);

  const fetchDashboardData = async () => {
    setLoading(true);
    setError('');
    try {
      const tenantsRes = await api.admin.getTenants();
      setTenants(tenantsRes);
      
      const healthRes = await api.admin.getSystemHealth();
      setHealth(healthRes);
      
      const monRes = await api.admin.getMonitoring();
      setMonitoring(monRes);
      
      const usageRes = await api.admin.getUsage();
      setUsage(usageRes);
      
      const logsRes = await api.admin.getAuditLogs(100);
      setAuditLogs(logsRes);
      
      const secRes = await api.admin.getSecurityCenter();
      setSecurityCenter(secRes);
      
      const payRes = await api.admin.getPayments();
      setPayments(payRes);
      
      const storageRes = await api.admin.getStorageReport();
      setStorageReport(storageRes);
    } catch (err: any) {
      if (err.message && err.message.includes('Authentication expired')) {
        localStorage.removeItem('replyos_admin_token');
        router.push('/admin/login');
      } else {
        setError(err.message || 'Failed loading master admin plane data.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    api.logout();
  };

  const handleEmergencyLock = async (lock: boolean) => {
    setActionLoading(true);
    setError('');
    setSuccessMsg('');
    try {
      let res;
      if (lock) {
        res = await api.admin.emergencyLock();
      } else {
        res = await api.admin.emergencyUnlock();
      }
      setSuccessMsg(res.message);
      await fetchDashboardData();
    } catch (err: any) {
      setError(err.message || 'Emergency lockdown control failed.');
    } finally {
      setActionLoading(false);
    }
  };

  // Administrative tenant lifecycle controls
  const handleTenantAction = async (tenantId: string, action: string, payload?: any) => {
    setActionLoading(true);
    setError('');
    setSuccessMsg('');
    try {
      const tenant = tenants.find(t => t.id === tenantId);
      if (tenant && isProtectedTenant(tenant)) {
        if (['suspend', 'toggle_policy', 'purge', 'revoke_sessions', 'force_logout', 'revoke_access', 'terminate'].includes(action)) {
          setError('Cannot execute destructive actions on the administrative System Operations tenant.');
          setActionLoading(false);
          return;
        }
      }
      let resMsg = '';
      if (action === 'suspend') {
        const res = await api.admin.suspendTenant(tenantId);
        resMsg = res.message;
      } else if (action === 'reactivate') {
        const res = await api.admin.reactivateTenant(tenantId);
        resMsg = res.message;
      } else if (action === 'reset_usage') {
        const res = await api.admin.resetUsage(tenantId);
        resMsg = res.message;
      } else if (action === 'revoke_sessions') {
        const res = await api.admin.revokeSessions(tenantId);
        resMsg = res.message;
      } else if (action === 'force_logout') {
        const res = await api.admin.forceLogout(tenantId);
        resMsg = res.message;
      } else if (action === 'grant_access') {
        const res = await api.admin.grantAccess(tenantId);
        resMsg = res.message;
      } else if (action === 'revoke_access') {
        const res = await api.admin.revokeAccess(tenantId);
        resMsg = res.message;
      } else if (action === 'impersonate') {
        const res = await api.admin.impersonate(tenantId);
        // Save token & tenant under customer keys
        localStorage.setItem('saas_token', res.access_token);
        localStorage.setItem('saas_tenant_id', res.tenant_id);
        localStorage.setItem('saas_role', res.role);
        window.open('/dashboard', '_blank');
        resMsg = 'Troubleshooting impersonation token generated. Opened customer dashboard.';
      } else if (action === 'toggle_policy') {
        const res = await api.admin.setRetentionPolicy(tenantId, { policy: payload });
        resMsg = res.message;
      } else if (action === 'purge') {
        const res = await api.admin.purgeTenant(tenantId);
        resMsg = res.message;
      }
      
      setSuccessMsg(resMsg);
      await fetchDashboardData();
    } catch (err: any) {
      setError(err.message || 'Action command failed.');
    } finally {
      setActionLoading(false);
    }
  };

  // Modal forms submission
  const handleModalSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeTenant || !modalType) return;
    
    setActionLoading(true);
    setError('');
    setSuccessMsg('');
    try {
      if (isProtectedTenant(activeTenant) && modalType === 'terminate') {
        setError('Cannot terminate the administrative System Operations tenant.');
        setActionLoading(false);
        return;
      }
      let resMsg = '';
      if (modalType === 'plan') {
        const res = await api.admin.changePlan(activeTenant.id, planForm);
        resMsg = `Subscription for ${activeTenant.name} successfully updated.`;
      } else if (modalType === 'quota') {
        const res = await api.admin.overrideQuotas(activeTenant.id, quotaForm);
        resMsg = `Quotas for ${activeTenant.name} successfully overridden.`;
      } else if (modalType === 'terminate') {
        const res = await api.admin.terminateTenant(activeTenant.id, { mode: terminateMode });
        resMsg = res.message;
      }
      
      setSuccessMsg(resMsg);
      setModalType(null);
      await fetchDashboardData();
    } catch (err: any) {
      setError(err.message || 'Modal update failed.');
    } finally {
      setActionLoading(false);
    }
  };

  // Setup TOTP 2FA for Admin Account
  const handleTotpSetupStart = async () => {
    setActionLoading(true);
    setError('');
    try {
      const res = await api.admin.totpSetup();
      setTotpSecret(res.secret);
      setTotpQr(res.otpauth_uri);
      setTotpSetupStep('generated');
    } catch (err: any) {
      setError(err.message || 'Failed generating TOTP secrets.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleTotpVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!totpVerifyCode) return;
    
    setActionLoading(true);
    setError('');
    try {
      const res = await api.admin.totpEnable({ code: totpVerifyCode });
      setTotpRecoveryCodes(res.recovery_codes);
      setTotpSetupStep('locked');
      setSuccessMsg(res.message);
      await fetchDashboardData();
    } catch (err: any) {
      setError(err.message || '2FA verification code mismatch.');
    } finally {
      setActionLoading(false);
    }
  };

  // Maintenance Broadcast Trigger
  const handleMaintenanceBroadcast = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!maintenanceMsg) return;
    
    setActionLoading(true);
    setError('');
    setSuccessMsg('');
    try {
      const res = await api.admin.broadcastMaintenance(maintenanceMsg);
      setSuccessMsg(res.message);
      setMaintenanceMsg('');
    } catch (err: any) {
      setError(err.message || 'Maintenance warning broadcast failed.');
    } finally {
      setActionLoading(false);
    }
  };

  // Manual cron triggers
  const handleTriggerCron = async () => {
    setActionLoading(true);
    setError('');
    setSuccessMsg('');
    try {
      const res = await api.admin.triggerCron();
      setSuccessMsg(res.message);
      await fetchDashboardData();
    } catch (err: any) {
      setError(err.message || 'Failed queueing background cron triggers.');
    } finally {
      setActionLoading(false);
    }
  };

  // Calculations
  const calculatedRevenue = payments
    .filter(p => p.status === 'captured')
    .reduce((sum, p) => sum + (p.amount / 100), 0);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-violet-600/40">
      {/* GLOW DECORATIONS */}
      <div className="absolute top-0 right-0 w-[40%] h-[40%] bg-violet-600/5 rounded-full blur-[160px] pointer-events-none"></div>
      <div className="absolute bottom-0 left-0 w-[40%] h-[40%] bg-pink-600/5 rounded-full blur-[160px] pointer-events-none"></div>

      {/* TOP HEADER */}
      <header className="border-b border-white/5 bg-slate-950/80 backdrop-blur-xl sticky top-0 z-40 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-violet-600 to-indigo-500 flex items-center justify-center border border-white/10 shadow-lg shadow-violet-500/10">
            <Shield className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight bg-clip-text bg-gradient-to-r from-white via-slate-100 to-slate-400">ReplyOS Control Plane</h1>
            <p className="text-[10px] text-slate-500 font-mono tracking-widest uppercase">System Control Center</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <button 
            onClick={fetchDashboardData}
            disabled={loading}
            className="p-2.5 bg-slate-900 border border-white/5 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800/80 transition-all disabled:opacity-40"
            title="Reload telemetry gauges"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </button>

          <button
            onClick={handleLogout}
            className="px-4 py-2 bg-rose-600/10 hover:bg-rose-600/20 border border-rose-500/20 hover:border-rose-500/40 text-rose-300 font-medium text-xs rounded-xl flex items-center gap-2 transition-all duration-300"
          >
            <LogOut className="h-3.5 w-3.5" />
            <span>Revoke Admin Access</span>
          </button>
        </div>
      </header>

      {/* MAIN CONTAINER */}
      <main className="flex-1 p-6 max-w-7xl w-full mx-auto space-y-6 z-10 relative">
        {/* SUCCESS/ERRORS ALERTS */}
        {error && (
          <div className="p-4 bg-rose-950/40 border border-rose-500/30 text-rose-300 rounded-2xl text-xs flex items-start gap-3 shadow-xl">
            <AlertTriangle className="h-5 w-5 mt-0.5 shrink-0 text-rose-400" />
            <div>
              <span className="font-semibold block mb-0.5">Execution Interrupted</span>
              <span>{error}</span>
            </div>
          </div>
        )}
        {successMsg && (
          <div className="p-4 bg-emerald-950/40 border border-emerald-500/30 text-emerald-300 rounded-2xl text-xs flex items-start gap-3 shadow-xl">
            <ShieldCheck className="h-5 w-5 mt-0.5 shrink-0 text-emerald-400" />
            <div>
              <span className="font-semibold block mb-0.5">Control Action Succeeded</span>
              <span>{successMsg}</span>
            </div>
          </div>
        )}

        {/* METRICS ROW */}
        {!loading && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-slate-900/40 border border-white/5 rounded-2xl p-5 relative overflow-hidden backdrop-blur-md">
              <div className="flex items-center justify-between mb-3 text-slate-400">
                <span className="text-xs font-semibold uppercase tracking-wider">Tenant Entities</span>
                <Users className="h-4 w-4 text-violet-400" />
              </div>
              <div className="flex items-baseline gap-2.5">
                <span className="text-3xl font-bold tracking-tight text-white">{tenants.length}</span>
                <span className="text-[10px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full font-medium">
                  {tenants.filter(t => t.status === 'active').length} Active
                </span>
              </div>
              <div className="flex justify-between items-center text-[10px] text-slate-500 mt-2.5 border-t border-white/5 pt-2">
                <span>Suspended: {tenants.filter(t => t.status === 'suspended').length}</span>
                <span>Terminated: {tenants.filter(t => t.status === 'TERMINATED').length}</span>
              </div>
            </div>

            <div className="bg-slate-900/40 border border-white/5 rounded-2xl p-5 relative overflow-hidden backdrop-blur-md">
              <div className="flex items-center justify-between mb-3 text-slate-400">
                <span className="text-xs font-semibold uppercase tracking-wider">Telemetry Revenue</span>
                <Coins className="h-4 w-4 text-emerald-400" />
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-3xl font-bold tracking-tight text-white">${calculatedRevenue.toLocaleString('en-US', { minimumFractionDigits: 0 })}</span>
                <span className="text-[10px] text-slate-400 uppercase tracking-widest font-mono">Captured</span>
              </div>
              <div className="flex justify-between items-center text-[10px] text-slate-500 mt-2.5 border-t border-white/5 pt-2">
                <span>Starter: {tenants.filter(t => t.subscription.plan_tier === 'starter').length}</span>
                <span>Pro: {tenants.filter(t => t.subscription.plan_tier === 'pro').length}</span>
              </div>
            </div>

            <div className="bg-slate-900/40 border border-white/5 rounded-2xl p-5 relative overflow-hidden backdrop-blur-md">
              <div className="flex items-center justify-between mb-3 text-slate-400">
                <span className="text-xs font-semibold uppercase tracking-wider">WhatsApp Channels</span>
                <Activity className="h-4 w-4 text-sky-400" />
              </div>
              <div className="flex items-baseline gap-2.5">
                <span className="text-3xl font-bold tracking-tight text-white">
                  {tenants.reduce((sum, t) => sum + t.sessions.length, 0)}
                </span>
                <span className="text-[10px] text-sky-400 bg-sky-500/10 border border-sky-500/20 px-2 py-0.5 rounded-full font-medium">
                  {tenants.reduce((sum, t) => sum + t.sessions.filter((s: any) => s.status === 'connected').length, 0)} Connected
                </span>
              </div>
              <div className="flex justify-between items-center text-[10px] text-slate-500 mt-2.5 border-t border-white/5 pt-2">
                <span>Active WS sockets: {monitoring.websocket_health.active_connections || 0}</span>
                <span>Queues size: {monitoring.redis_queues.celery_queue_size || 0}</span>
              </div>
            </div>

            <div className="bg-slate-900/40 border border-white/5 rounded-2xl p-5 relative overflow-hidden backdrop-blur-md">
              <div className="flex items-center justify-between mb-3 text-slate-400">
                <span className="text-xs font-semibold uppercase tracking-wider">Operational Traffic</span>
                <MessageSquare className="h-4 w-4 text-pink-400" />
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-3xl font-bold tracking-tight text-white">{usage.global_usage.total_messages || 0}</span>
                <span className="text-[10px] text-slate-400">Logs Inserted</span>
              </div>
              <div className="flex justify-between items-center text-[10px] text-slate-500 mt-2.5 border-t border-white/5 pt-2">
                <span>Outbound: {usage.global_usage?.outbound_messages || 0}</span>
                <span>Avg AI Latency: {((usage.global_usage?.avg_ai_latency_ms || 0) / 1000).toFixed(1)}s</span>
              </div>
            </div>
          </div>
        )}

        {/* TABS SELECTOR */}
        <div className="border-b border-white/5 flex gap-6">
          <button
            onClick={() => setActiveTab('tenants')}
            className={`pb-4 text-sm font-semibold tracking-wide border-b-2 transition-all ${activeTab === 'tenants' ? 'border-violet-500 text-white' : 'border-transparent text-slate-400 hover:text-slate-200'}`}
          >
            Tenant Lifecycle Registry
          </button>
          <button
            onClick={() => setActiveTab('observability')}
            className={`pb-4 text-sm font-semibold tracking-wide border-b-2 transition-all ${activeTab === 'observability' ? 'border-violet-500 text-white' : 'border-transparent text-slate-400 hover:text-slate-200'}`}
          >
            System Realtime Diagnostics
          </button>
          <button
            onClick={() => setActiveTab('audits')}
            className={`pb-4 text-sm font-semibold tracking-wide border-b-2 transition-all ${activeTab === 'audits' ? 'border-violet-500 text-white' : 'border-transparent text-slate-400 hover:text-slate-200'}`}
          >
            Permanent Administrative Audit
          </button>
          <button
            onClick={() => setActiveTab('security')}
            className={`pb-4 text-sm font-semibold tracking-wide border-b-2 transition-all ${activeTab === 'security' ? 'border-violet-500 text-white' : 'border-transparent text-slate-400 hover:text-slate-200'}`}
          >
            Control Plane Hardening
          </button>
          <button
            onClick={() => setActiveTab('settings')}
            className={`pb-4 text-sm font-semibold tracking-wide border-b-2 transition-all ${activeTab === 'settings' ? 'border-violet-500 text-white' : 'border-transparent text-slate-400 hover:text-slate-200'}`}
          >
            Operational settings
          </button>
        </div>

        {/* TAB CONTENTS: TENANTS REGISTRY */}
        {activeTab === 'tenants' && !loading && (
          <div className="space-y-6">
            <div className="bg-slate-900/40 border border-white/5 rounded-2xl overflow-hidden backdrop-blur-md shadow-xl">
              <div className="px-6 py-5 border-b border-white/5 flex items-center justify-between">
                <div>
                  <h3 className="font-bold text-white tracking-wide">Tenant Entities</h3>
                  <p className="text-xs text-slate-500">Configure parameters, quotas, data policies, or trigger emergency suspensions.</p>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-white/5 text-slate-400 font-bold uppercase tracking-wider text-[10px]">
                      <th className="px-6 py-4">Subdomain / Domain</th>
                      <th className="px-6 py-4">Lifecycle Status</th>
                      <th className="px-6 py-4">Subscription Plan</th>
                      <th className="px-6 py-4">Billing End</th>
                      <th className="px-6 py-4">Linked Session status</th>
                      <th className="px-6 py-4">Data Policy</th>
                      <th className="px-6 py-4 text-right">Operational Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5 text-slate-300">
                    {tenants.map((t) => (
                      <tr key={t.id} className="hover:bg-white/2 transition-colors">
                        <td className="px-6 py-4">
                          <div className="font-bold text-white text-sm">{t.name}</div>
                          <div className="text-[10px] text-slate-500 font-mono mt-0.5">{t.subdomain}.replyos.com</div>
                        </td>
                        <td className="px-6 py-4">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border ${
                            t.status === 'active' ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' :
                            t.status === 'suspended' ? 'bg-rose-500/10 border-rose-500/20 text-rose-400' :
                            t.status === 'PENDING TERMINATION' ? 'bg-amber-500/10 border-amber-500/20 text-amber-400 animate-pulse' :
                            'bg-slate-800 border-slate-700 text-slate-400'
                          }`}>
                            {t.status}
                          </span>
                          {t.termination_grace_period_ends && (
                            <div className="text-[9px] text-rose-400/80 mt-1 font-mono">
                              Expires: {new Date(t.termination_grace_period_ends).toLocaleTimeString()}
                            </div>
                          )}
                        </td>
                        <td className="px-6 py-4">
                          <div className="capitalize font-semibold text-slate-200">{t.subscription.plan_tier} Plan</div>
                          <div className="text-[10px] text-slate-500 mt-0.5">Bots: {t.subscription.max_bots} | Msg: {t.subscription.max_messages}</div>
                        </td>
                        <td className="px-6 py-4 font-mono text-slate-400">
                          {t.subscription.current_period_end 
                            ? new Date(t.subscription.current_period_end).toLocaleDateString()
                            : 'N/A'
                          }
                        </td>
                        <td className="px-6 py-4">
                          {t.sessions.length > 0 ? (
                            <div className="space-y-1">
                              {t.sessions.map((s: any) => (
                                <div key={s.id} className="flex items-center gap-1.5 font-mono text-[10px]">
                                  <span className={`h-1.5 w-1.5 rounded-full ${s.status === 'connected' ? 'bg-emerald-400 shadow-sm shadow-emerald-400/30' : 'bg-rose-400'}`}></span>
                                  <span className="text-slate-300">{s.phone || 'No phone'}</span>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <span className="text-slate-500">No session</span>
                          )}
                        </td>
                        <td className="px-6 py-4">
                          {isProtectedTenant(t) ? (
                            <span className="text-[10px] text-slate-500 font-mono">System Managed</span>
                          ) : (
                            <button
                              onClick={() => handleTenantAction(t.id, 'toggle_policy', t.data_retention_policy === 'archive' ? 'delete' : 'archive')}
                              disabled={actionLoading}
                              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-[10px] font-bold tracking-wide transition-all ${
                                t.data_retention_policy === 'delete' 
                                  ? 'bg-rose-500/10 border-rose-500/20 text-rose-300 hover:bg-rose-500/20' 
                                  : 'bg-slate-900 border-white/5 text-slate-400 hover:text-white'
                              }`}
                            >
                              <span>{t.data_retention_policy === 'delete' ? 'Delete Mode' : 'Archive Mode'}</span>
                            </button>
                          )}
                        </td>
                        <td className="px-6 py-4 text-right space-y-1.5">
                          {isProtectedTenant(t) ? (
                            <div className="flex justify-end">
                              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold border bg-blue-500/10 border-blue-500/20 text-blue-400 shadow-sm shadow-blue-500/5">
                                <Shield className="h-3 w-3 text-blue-400 animate-pulse" />
                                Protected System Tenant
                              </span>
                            </div>
                          ) : (
                            <>
                              <div className="flex justify-end gap-1.5">
                                {t.status !== 'TERMINATED' && (
                                  t.status !== 'active' ? (
                                    <button
                                      onClick={() => handleTenantAction(t.id, 'reactivate')}
                                      disabled={actionLoading}
                                      className="px-2.5 py-1 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 hover:bg-emerald-500/20 rounded-md font-bold text-[10px]"
                                      title="Restore Tenant Workspace"
                                    >
                                      Restore Tenant
                                    </button>
                                  ) : (
                                    <button
                                      onClick={() => handleTenantAction(t.id, 'suspend')}
                                      disabled={actionLoading}
                                      className="px-2.5 py-1 bg-rose-500/10 border border-rose-500/20 text-rose-400 hover:bg-rose-500/20 rounded-md font-bold text-[10px]"
                                    >
                                      Suspend
                                    </button>
                                  )
                                )}

                                {t.status !== 'TERMINATED' && (
                                  <>
                                    <button
                                      onClick={() => {
                                        setActiveTenant(t);
                                        setModalType('plan');
                                        setPlanForm({
                                          plan_tier: t.subscription.plan_tier,
                                          max_bots: t.subscription.max_bots,
                                          max_messages: t.subscription.max_messages,
                                          days: 30
                                        });
                                      }}
                                      className="px-2.5 py-1 bg-slate-900 border border-white/5 hover:bg-slate-800 text-slate-300 rounded-md font-bold text-[10px]"
                                    >
                                      Edit Plan
                                    </button>

                                    <button
                                      onClick={() => {
                                        setActiveTenant(t);
                                        setModalType('plan');
                                        setPlanForm({
                                          plan_tier: t.subscription.plan_tier,
                                          max_bots: t.subscription.max_bots,
                                          max_messages: t.subscription.max_messages,
                                          days: 30
                                        });
                                      }}
                                      className="px-2.5 py-1 bg-indigo-600/10 border border-indigo-500/20 hover:bg-indigo-500/20 text-indigo-400 rounded-md font-bold text-[10px]"
                                      title="Renew / Extend Subscription"
                                    >
                                      Renew Subscription
                                    </button>

                                    <button
                                      onClick={() => {
                                        setActiveTenant(t);
                                        setModalType('quota');
                                        setQuotaForm({
                                          max_bots: t.subscription.max_bots,
                                          max_messages: t.subscription.max_messages
                                        });
                                      }}
                                      className="px-2.5 py-1 bg-slate-900 border border-white/5 hover:bg-slate-800 text-slate-300 rounded-md font-bold text-[10px]"
                                    >
                                      Quota
                                    </button>

                                    <button
                                      onClick={() => handleTenantAction(t.id, 'impersonate')}
                                      disabled={actionLoading}
                                      className="px-2.5 py-1 bg-violet-600/10 border border-violet-500/20 text-violet-400 hover:bg-violet-500/20 rounded-md font-bold text-[10px]"
                                    >
                                      Impersonate
                                    </button>
                                  </>
                                )}
                              </div>

                              <div className="flex justify-end gap-1.5">
                                {t.status !== 'TERMINATED' && (
                                  <>
                                    <button
                                      onClick={() => handleTenantAction(t.id, 'reset_usage')}
                                      disabled={actionLoading}
                                      className="px-2 py-0.5 bg-slate-900 border border-white/5 hover:bg-slate-800 text-slate-400 hover:text-white rounded text-[9px]"
                                      title="Reset Counters"
                                    >
                                      Reset Counters
                                    </button>
                                    <button
                                      onClick={() => handleTenantAction(t.id, 'revoke_sessions')}
                                      disabled={actionLoading}
                                      className="px-2 py-0.5 bg-slate-900 border border-white/5 hover:bg-slate-800 text-slate-400 hover:text-white rounded text-[9px]"
                                      title="Disconnect Sessions"
                                    >
                                      Disconnect Sessions
                                    </button>
                                    <button
                                      onClick={() => handleTenantAction(t.id, 'grant_access')}
                                      disabled={actionLoading}
                                      className="px-2 py-0.5 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 hover:bg-emerald-500/20 rounded text-[9px] font-semibold"
                                    >
                                      Grant Access
                                    </button>
                                    <button
                                      onClick={() => handleTenantAction(t.id, 'revoke_access')}
                                      disabled={actionLoading}
                                      className="px-2 py-0.5 bg-rose-500/10 border border-rose-500/20 text-rose-400 hover:bg-rose-500/20 rounded text-[9px] font-semibold"
                                    >
                                      Revoke Access
                                    </button>
                                    <button
                                      onClick={() => {
                                        setActiveTenant(t);
                                        setModalType('terminate');
                                        setTerminateMode('graceful');
                                      }}
                                      className="px-2 py-0.5 bg-rose-600/10 border border-rose-500/20 hover:bg-rose-500/20 text-rose-400 rounded text-[9px] font-semibold"
                                    >
                                      Terminate Tenant
                                    </button>
                                  </>
                                )}
                                {(t.data_retention_policy === 'delete' || t.status === 'TERMINATED') && (
                                  <button
                                    onClick={() => {
                                      if (confirm('Verify: Permanently hard-purge this tenant space? This transaction cannot be undone.')) {
                                        handleTenantAction(t.id, 'purge');
                                      }
                                    }}
                                    className="px-2 py-0.5 bg-rose-950/40 border border-rose-500/30 text-rose-300 hover:bg-rose-950/60 rounded text-[9px] font-semibold shadow-md"
                                    title="Manual secure hard purge"
                                  >
                                    Purge
                                  </button>
                                )}
                              </div>
                            </>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* TAB CONTENTS: SYSTEM OBSERVABILITY */}
        {activeTab === 'observability' && !loading && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* SYSTEM HARDWARE GAUGES */}
              <div className="bg-slate-900/40 border border-white/5 rounded-2xl p-6 backdrop-blur-md shadow-xl space-y-4">
                <h3 className="font-bold text-white text-sm uppercase tracking-wider border-b border-white/5 pb-2.5">Telemetry Server</h3>
                <div className="space-y-4">
                  <div>
                    <div className="flex justify-between text-xs text-slate-400 mb-1">
                      <span>CPU Utilization</span>
                      <span className="font-bold text-white font-mono">{health.system.cpu_percent || 0}%</span>
                    </div>
                    <div className="w-full bg-slate-950/60 rounded-full h-2.5 border border-white/5 relative overflow-hidden">
                      <div className="bg-gradient-to-r from-violet-500 to-indigo-500 h-full rounded-full" style={{ width: `${health.system.cpu_percent || 0}%` }}></div>
                    </div>
                  </div>

                  <div>
                    <div className="flex justify-between text-xs text-slate-400 mb-1">
                      <span>Memory (RAM) Footprint</span>
                      <span className="font-bold text-white font-mono">{health.system.ram_percent || 0}%</span>
                    </div>
                    <div className="w-full bg-slate-950/60 rounded-full h-2.5 border border-white/5 relative overflow-hidden">
                      <div className="bg-gradient-to-r from-pink-500 to-rose-500 h-full rounded-full" style={{ width: `${health.system.ram_percent || 0}%` }}></div>
                    </div>
                  </div>

                  <div>
                    <div className="flex justify-between text-xs text-slate-400 mb-1">
                      <span>Solid State Storage (SSD)</span>
                      <span className="font-bold text-white font-mono">{health.system.disk_percent || 0}%</span>
                    </div>
                    <div className="w-full bg-slate-950/60 rounded-full h-2.5 border border-white/5 relative overflow-hidden">
                      <div className="bg-gradient-to-r from-amber-500 to-orange-500 h-full rounded-full" style={{ width: `${health.system.disk_percent || 0}%` }}></div>
                    </div>
                  </div>
                </div>
              </div>

              {/* SERVICES HEALTH GAUGE */}
              <div className="bg-slate-900/40 border border-white/5 rounded-2xl p-6 backdrop-blur-md shadow-xl md:col-span-2 space-y-4">
                <h3 className="font-bold text-white text-sm uppercase tracking-wider border-b border-white/5 pb-2.5">Services status Engine</h3>
                
                <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
                  <div className="bg-slate-950/60 border border-white/5 p-4 rounded-xl flex items-center justify-between">
                    <div>
                      <div className="text-[10px] text-slate-500 uppercase tracking-widest font-bold mb-1">PostgreSQL</div>
                      <div className={`text-xs font-bold ${health.services?.postgres === 'online' ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {health.services?.postgres === 'online' ? 'ONLINE' : 'OFFLINE'}
                      </div>
                    </div>
                    <div className={`h-2 w-2 rounded-full ${health.services?.postgres === 'online' ? 'bg-emerald-400' : 'bg-rose-400'}`}></div>
                  </div>

                  <div className="bg-slate-950/60 border border-white/5 p-4 rounded-xl flex items-center justify-between">
                    <div>
                      <div className="text-[10px] text-slate-500 uppercase tracking-widest font-bold mb-1">Redis Broker</div>
                      <div className={`text-xs font-bold ${health.services?.redis === 'online' ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {health.services?.redis === 'online' ? 'ONLINE' : 'OFFLINE'}
                      </div>
                      {health.services?.redis === 'online' && (
                        <div className="text-[9px] text-slate-400 mt-1 font-mono">Ping: {health.services?.redis_latency_ms}ms</div>
                      )}
                    </div>
                    <div className={`h-2 w-2 rounded-full ${health.services?.redis === 'online' ? 'bg-emerald-400' : 'bg-rose-400'}`}></div>
                  </div>

                  <div className="bg-slate-950/60 border border-white/5 p-4 rounded-xl flex items-center justify-between">
                    <div>
                      <div className="text-[10px] text-slate-500 uppercase tracking-widest font-bold mb-1">WhatsApp Engine</div>
                      <div className={`text-xs font-bold ${health.services?.whatsapp_engine === 'healthy' ? 'text-emerald-400' : (health.services?.whatsapp_engine === 'offline' ? 'text-rose-400' : 'text-amber-400')}`}>
                        {(health.services?.whatsapp_engine || 'offline').toUpperCase()}
                      </div>
                      {health.services?.whatsapp_active_sessions !== undefined && (
                        <div className="text-[9px] text-slate-400 mt-1 font-mono">Sessions: {health.services?.whatsapp_active_sessions}</div>
                      )}
                    </div>
                    <div className={`h-2 w-2 rounded-full ${health.services?.whatsapp_engine === 'healthy' ? 'bg-emerald-400' : (health.services?.whatsapp_engine === 'offline' ? 'bg-rose-400' : 'bg-amber-400')}`}></div>
                  </div>

                  <div className="bg-slate-950/60 border border-white/5 p-4 rounded-xl flex items-center justify-between">
                    <div>
                      <div className="text-[10px] text-slate-500 uppercase tracking-widest font-bold mb-1">Ollama AI Runtime</div>
                      <div className={`text-xs font-bold ${health.services?.ai_runtime === 'online' ? 'text-emerald-400' : (health.services?.ai_runtime === 'offline' ? 'text-rose-400' : 'text-amber-400')}`}>
                        {(health.services?.ai_runtime || 'offline').toUpperCase()}
                      </div>
                    </div>
                    <div className={`h-2 w-2 rounded-full ${health.services?.ai_runtime === 'online' ? 'bg-emerald-400' : (health.services?.ai_runtime === 'offline' ? 'bg-rose-400' : 'bg-amber-400')}`}></div>
                  </div>

                  <div className="bg-slate-950/60 border border-white/5 p-4 rounded-xl flex items-center justify-between">
                    <div>
                      <div className="text-[10px] text-slate-500 uppercase tracking-widest font-bold mb-1">WebSockets Pipe</div>
                      <div className={`text-xs font-bold ${
                        health.services?.websockets?.status === 'online' 
                          ? 'text-emerald-400' 
                          : health.services?.websockets?.status === 'degraded'
                          ? 'text-amber-400'
                          : 'text-rose-400'
                      }`}>
                        {(health.services?.websockets?.status || 'offline').toUpperCase()}
                      </div>
                      <div className="text-[9px] text-slate-400 mt-1 font-mono">Sockets: {health.services?.websockets?.active_connections || 0}</div>
                    </div>
                    <div className={`h-2 w-2 rounded-full ${
                      health.services?.websockets?.status === 'online' 
                        ? 'bg-emerald-400' 
                        : health.services?.websockets?.status === 'degraded'
                        ? 'bg-amber-400'
                        : 'bg-rose-400'
                    }`}></div>
                  </div>

                  <div className="bg-slate-950/60 border border-white/5 p-4 rounded-xl flex items-center justify-between">
                    <div>
                      <div className="text-[10px] text-slate-500 uppercase tracking-widest font-bold mb-1">Celery Worker Node</div>
                      <div className={`text-xs font-bold ${health.services?.celery_workers?.status === 'online' ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {(health.services?.celery_workers?.status || 'offline').toUpperCase()}
                      </div>
                      <div className="text-[9px] text-slate-400 mt-1 font-mono">Queue: {health.services?.celery_workers?.queue_size || 0} pending</div>
                    </div>
                    <div className={`h-2 w-2 rounded-full ${health.services?.celery_workers?.status === 'online' ? 'bg-emerald-400' : 'bg-rose-400'}`}></div>
                  </div>
                </div>
              </div>
            </div>

            {/* QUEUE HEALTH & DISPATCH FAILURES */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="bg-slate-900/40 border border-white/5 rounded-2xl p-6 backdrop-blur-md shadow-xl space-y-3">
                <h4 className="font-bold text-white text-sm border-b border-white/5 pb-2">Active Redis WhatsApp queues</h4>
                {Object.keys(monitoring.redis_queues?.whatsapp_queues || {}).length > 0 ? (
                  <div className="space-y-2">
                    {Object.entries(monitoring.redis_queues?.whatsapp_queues || {}).map(([key, size]: any) => (
                      <div key={key} className="flex items-center justify-between text-xs bg-slate-950/40 border border-white/5 p-3 rounded-lg font-mono">
                        <span className="text-slate-400">{key}</span>
                        <span className="font-bold text-white">{size} pending</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-xs text-slate-500 text-center py-6">All queues empty. Broadcast pipelines cleared.</div>
                )}
              </div>

              <div className="bg-slate-900/40 border border-white/5 rounded-2xl p-6 backdrop-blur-md shadow-xl space-y-4">
                <h4 className="font-bold text-white text-sm border-b border-white/5 pb-2">Failed payment capture trace</h4>
                {(monitoring.failed_payments?.recent?.length || 0) > 0 ? (
                  <div className="space-y-2">
                    {monitoring.failed_payments.recent.map((p: any) => (
                      <div key={p.id} className="flex justify-between text-xs bg-slate-950/40 border border-white/5 p-3 rounded-lg font-mono">
                        <div>
                          <span className="text-rose-400 block font-bold">Failed Payment</span>
                          <span className="text-[10px] text-slate-500">Order: {p.order_id}</span>
                        </div>
                        <div className="text-right">
                          <span className="font-bold text-white block">${(p.amount / 100).toFixed(2)}</span>
                          <span className="text-[9px] text-slate-400">{new Date(p.created_at).toLocaleDateString()}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-xs text-slate-500 text-center py-6">No payment failures detected. Invoice structures healthy.</div>
                )}
              </div>
            </div>

            {/* STORAGE TELEMETRY FOOTPRINT */}
            {storageReport && (
              <div className="bg-slate-900/40 border border-white/5 rounded-2xl p-6 backdrop-blur-md shadow-xl space-y-4">
                <div className="flex items-center justify-between border-b border-white/5 pb-3">
                  <div>
                    <h3 className="font-bold text-white text-sm uppercase tracking-wider flex items-center gap-2">
                      <HardDrive className="h-4.5 w-4.5 text-violet-400" />
                      <span>Solid State Storage Dashboard</span>
                    </h3>
                    <p className="text-[10px] text-slate-500 mt-0.5 font-semibold">Real-time disk breakdown and Docker cache footprint.</p>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="text-right text-xs">
                      <span className="text-slate-400 font-semibold block text-[10px] uppercase">Total Size</span>
                      <span className="font-bold text-white font-mono">{formatBytes(storageReport.total_storage)}</span>
                    </div>
                    <div className="text-right text-xs">
                      <span className="text-rose-400 font-semibold block text-[10px] uppercase">Used Space</span>
                      <span className="font-bold text-rose-300 font-mono">{formatBytes(storageReport.used_storage)}</span>
                    </div>
                    <div className="text-right text-xs">
                      <span className="text-emerald-400 font-semibold block text-[10px] uppercase">Free Space</span>
                      <span className="font-bold text-emerald-300 font-mono">{formatBytes(storageReport.free_storage)}</span>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                  <div className="bg-slate-950/60 border border-white/5 p-4 rounded-xl">
                    <div className="text-[9px] text-slate-500 uppercase tracking-widest font-bold mb-1">Docker Images</div>
                    <div className="text-xs font-bold text-slate-200 font-mono">{formatBytes(storageReport.docker_images_size)}</div>
                  </div>
                  <div className="bg-slate-950/60 border border-white/5 p-4 rounded-xl">
                    <div className="text-[9px] text-slate-500 uppercase tracking-widest font-bold mb-1">Docker Volumes</div>
                    <div className="text-xs font-bold text-slate-200 font-mono">{formatBytes(storageReport.docker_volume_size)}</div>
                  </div>
                  <div className="bg-slate-950/60 border border-white/5 p-4 rounded-xl">
                    <div className="text-[9px] text-slate-500 uppercase tracking-widest font-bold mb-1">Docker Cache</div>
                    <div className="text-xs font-bold text-slate-200 font-mono">{formatBytes(storageReport.docker_cache_size)}</div>
                  </div>
                  <div className="bg-slate-950/60 border border-white/5 p-4 rounded-xl">
                    <div className="text-[9px] text-slate-500 uppercase tracking-widest font-bold mb-1">Container Logs</div>
                    <div className="text-xs font-bold text-slate-200 font-mono">{formatBytes(storageReport.container_logs_size)}</div>
                  </div>
                  <div className="bg-slate-950/60 border border-white/5 p-4 rounded-xl">
                    <div className="text-[9px] text-slate-500 uppercase tracking-widest font-bold mb-1">Database Size</div>
                    <div className="text-xs font-bold text-slate-200 font-mono">{formatBytes(storageReport.database_size)}</div>
                  </div>
                  <div className="bg-slate-950/60 border border-white/5 p-4 rounded-xl">
                    <div className="text-[9px] text-slate-500 uppercase tracking-widest font-bold mb-1">Redis Memory</div>
                    <div className="text-xs font-bold text-slate-200 font-mono">{formatBytes(storageReport.redis_size)}</div>
                  </div>
                  <div className="bg-slate-950/60 border border-white/5 p-4 rounded-xl">
                    <div className="text-[9px] text-slate-500 uppercase tracking-widest font-bold mb-1">Project Files</div>
                    <div className="text-xs font-bold text-slate-200 font-mono">{formatBytes(storageReport.project_files_size)}</div>
                  </div>
                  <div className="bg-slate-950/60 border border-white/5 p-4 rounded-xl">
                    <div className="text-[9px] text-slate-500 uppercase tracking-widest font-bold mb-1">User Manuals</div>
                    <div className="text-xs font-bold text-slate-200 font-mono">{formatBytes(storageReport.uploads_size)}</div>
                  </div>
                  <div className="bg-slate-950/60 border border-white/5 p-4 rounded-xl">
                    <div className="text-[9px] text-slate-500 uppercase tracking-widest font-bold mb-1">System Backups</div>
                    <div className="text-xs font-bold text-slate-200 font-mono">{formatBytes(storageReport.backups_size)}</div>
                  </div>
                  <div className="bg-slate-950/60 border border-white/5 p-4 rounded-xl">
                    <div className="text-[9px] text-slate-500 uppercase tracking-widest font-bold mb-1">Temporary Files</div>
                    <div className="text-xs font-bold text-slate-200 font-mono">{formatBytes(storageReport.temporary_files_size)}</div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB CONTENTS: AUDIT LOG HISTORY */}
        {activeTab === 'audits' && !loading && (
          <div className="bg-slate-900/40 border border-white/5 rounded-2xl overflow-hidden backdrop-blur-md shadow-xl">
            <div className="px-6 py-5 border-b border-white/5 flex items-center justify-between">
              <div>
                <h3 className="font-bold text-white tracking-wide">Administrative Audit Log history</h3>
                <p className="text-xs text-slate-500">Permanent record of actions compiled under PostgreSQL. Deleting these logs is strictly forbidden.</p>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-white/5 text-slate-400 font-bold uppercase tracking-wider text-[10px]">
                    <th className="px-6 py-4">Timestamp</th>
                    <th className="px-6 py-4">Action Dispatcher</th>
                    <th className="px-6 py-4">Action Type</th>
                    <th className="px-6 py-4">Affected tenant</th>
                    <th className="px-6 py-4">Resources</th>
                    <th className="px-6 py-4">Payload (State Changes)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 text-slate-300 font-mono text-[11px]">
                  {auditLogs.map((l) => (
                    <tr key={l.id} className="hover:bg-white/2 transition-colors">
                      <td className="px-6 py-4 text-slate-500">
                        {new Date(l.created_at).toLocaleString()}
                      </td>
                      <td className="px-6 py-4 text-violet-400 font-bold">
                        {l.admin_email}
                      </td>
                      <td className="px-6 py-4">
                        <span className="inline-flex px-2 py-0.5 rounded bg-violet-600/10 border border-violet-500/20 text-violet-300 font-semibold text-[10px]">
                          {l.action_type}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        {l.target_tenant_name ? (
                          <div>
                            <span className="font-bold text-slate-200 block">{l.target_tenant_name}</span>
                            <span className="text-[9px] text-slate-500">{l.target_tenant_subdomain}</span>
                          </div>
                        ) : (
                          <span className="text-slate-600">N/A</span>
                        )}
                      </td>
                      <td className="px-6 py-4 text-slate-400">
                        {l.affected_resources || 'general'}
                      </td>
                      <td className="px-6 py-4 text-slate-500 max-w-xs truncate" title={JSON.stringify(l.new_state || {})}>
                        {l.new_state ? (
                          <div className="text-[10px] bg-slate-950/60 p-2 border border-white/5 rounded">
                            <span className="text-slate-400 font-bold">New: </span>
                            {JSON.stringify(l.new_state)}
                          </div>
                        ) : (
                          <span>N/A</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* TAB CONTENTS: CONTROL PLANE HARDENING */}
        {activeTab === 'security' && !loading && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* BROADCAST & SYSTEM TRIGGERS */}
            <div className="space-y-6">
              <div className="bg-slate-900/40 border border-white/5 rounded-2xl p-6 backdrop-blur-md shadow-xl space-y-4">
                <h3 className="font-bold text-white text-sm uppercase tracking-wider border-b border-white/5 pb-2.5">Global broadcast control</h3>
                
                <form onSubmit={handleMaintenanceBroadcast} className="space-y-4">
                  <div>
                    <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">Maintenance warning broadcast alert</label>
                    <textarea
                      value={maintenanceMsg}
                      onChange={(e) => setMaintenanceMsg(e.target.value)}
                      placeholder="Enter a message to broadcast to all logged in tenant client dashboards immediately via WebSockets..."
                      rows={4}
                      className="w-full bg-slate-950/60 border border-white/5 rounded-xl p-4 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-violet-500/50"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={actionLoading || !maintenanceMsg}
                    className="px-4 py-2.5 bg-violet-600 hover:bg-violet-500 text-white font-semibold text-xs rounded-xl shadow-md transition-all"
                  >
                    Broadcast Warning Warning Alert
                  </button>
                </form>
              </div>

              <div className="bg-slate-900/40 border border-white/5 rounded-2xl p-6 backdrop-blur-md shadow-xl space-y-4">
                <h3 className="font-bold text-white text-sm uppercase tracking-wider border-b border-white/5 pb-2.5">System daemon cron control</h3>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Trigger manual evaluation loops. Commits 24-hour grace terminations immediately, schedules auto-renew collections, and checks alerts across celery queues.
                </p>
                <button
                  onClick={handleTriggerCron}
                  disabled={actionLoading}
                  className="w-full bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white py-3.5 rounded-xl font-semibold text-xs flex items-center justify-center gap-2 shadow-lg transition-all"
                >
                  <RefreshCw className={`h-4.5 w-4.5 ${actionLoading ? 'animate-spin' : ''}`} />
                  <span>Execute Cron Telemetries immediately</span>
                </button>
              </div>

              {/* EMERGENCY SYSTEM LOCKDOWN */}
              <div className="bg-slate-900/40 border border-white/5 rounded-2xl p-6 backdrop-blur-md shadow-xl space-y-4">
                <h3 className="font-bold text-white text-sm uppercase tracking-wider border-b border-white/5 pb-2.5 flex items-center gap-2">
                  <AlertOctagon className="h-4.5 w-4.5 text-rose-500" />
                  <span>Emergency System Lockdown</span>
                </h3>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Lock down all API services, customer dashboard sessions, and logins instantly. Super Admins bypass this blockout to manage troubleshooting and restoration.
                </p>
                <div className="flex items-center justify-between p-3.5 bg-slate-950/60 border border-white/5 rounded-xl">
                  <div className="text-xs">
                    <span className="text-slate-400 font-semibold block uppercase">Lockdown status</span>
                    <span className={`font-bold block ${health.emergency_system_lock ? 'text-rose-400' : 'text-emerald-400'}`}>
                      {health.emergency_system_lock ? '🚨 ACTIVE LOCKDOWN (BLOCKED)' : '🟢 DEACTIVATED (OPERATIONAL)'}
                    </span>
                  </div>
                  {health.emergency_system_lock ? (
                    <button
                      onClick={() => {
                        if (confirm('Verify: Emergency unlock the platform? This restores access to all tenants.')) {
                          handleEmergencyLock(false);
                        }
                      }}
                      disabled={actionLoading}
                      className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs rounded-xl shadow-md transition-all"
                    >
                      Emergency Unlock Platform
                    </button>
                  ) : (
                    <button
                      onClick={() => {
                        if (confirm('WARNING: Emergency lock the entire platform? All non-admin client traffic will be blocked instantly.')) {
                          handleEmergencyLock(true);
                        }
                      }}
                      disabled={actionLoading}
                      className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white font-semibold text-xs rounded-xl shadow-md transition-all"
                    >
                      Emergency Lock Platform
                    </button>
                  )}
                </div>
              </div>
            </div>

            {/* TOTP 2FA SETTINGS */}
            <div className="bg-slate-900/40 border border-white/5 rounded-2xl p-6 backdrop-blur-md shadow-xl space-y-6">
              <div className="border-b border-white/5 pb-3">
                <h3 className="font-bold text-white text-sm uppercase tracking-wider">Control Plane 2FA Lockout</h3>
                <p className="text-xs text-slate-500 mt-1">Enforce TOTP 2FA. Generates recovery tokens and keeps session secure.</p>
              </div>

              {totpSetupStep === 'idle' && (
                <div className="space-y-4 text-center py-6">
                  <div className="mx-auto h-12 w-12 rounded-xl bg-violet-600/10 border border-violet-500/20 flex items-center justify-center text-violet-400">
                    <ShieldCheck className="h-6 w-6" />
                  </div>
                  <div className="space-y-1">
                    <h4 className="font-bold text-white text-sm">2FA locks are currently disabled or inactive</h4>
                    <p className="text-xs text-slate-400 max-w-sm mx-auto">Click below to generate a new key and configure Google Authenticator or Microsoft Authenticator locks.</p>
                  </div>
                  <button
                    onClick={handleTotpSetupStart}
                    disabled={actionLoading}
                    className="px-4 py-2.5 bg-violet-600 hover:bg-violet-500 text-white font-bold text-xs rounded-xl transition-all"
                  >
                    Setup TOTP Multi-factor locks
                  </button>
                </div>
              )}

              {totpSetupStep === 'generated' && (
                <form onSubmit={handleTotpVerify} className="space-y-4">
                  <div className="p-3 bg-violet-500/10 border border-violet-500/20 rounded-xl">
                    <span className="text-violet-400 font-bold block text-xs mb-1">Verify Secret</span>
                    <p className="text-[11px] text-slate-400">
                      Scan the OTP key or enter the secret code: <span className="font-mono font-bold text-white block text-sm select-all mt-1 bg-slate-950 p-2 rounded tracking-widest text-center">{totpSecret}</span>
                    </p>
                  </div>

                  <div>
                    <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">Enter Authenticator 6-digit Code</label>
                    <input
                      type="text"
                      required
                      placeholder="000 000"
                      maxLength={6}
                      value={totpVerifyCode}
                      onChange={(e) => setTotpVerifyCode(e.target.value)}
                      className="w-full bg-slate-950/60 border border-white/5 rounded-xl p-3.5 text-center text-white tracking-widest font-mono text-base focus:outline-none"
                    />
                  </div>

                  <button
                    type="submit"
                    disabled={actionLoading || !totpVerifyCode}
                    className="w-full py-3 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs rounded-xl shadow-md transition-all"
                  >
                    Verify & lock Control Plane 2FA
                  </button>
                </form>
              )}

              {totpSetupStep === 'locked' && (
                <div className="space-y-4">
                  <div className="p-4 bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 rounded-xl flex gap-3 text-xs">
                    <ShieldCheck className="h-6 w-6 text-emerald-400 shrink-0 mt-0.5" />
                    <div>
                      <span className="font-bold block mb-1">Control Plane Locked & Active</span>
                      <p className="text-slate-400 leading-relaxed">Two-Factor Authentication is actively protecting this portal. Normal credentials logins are locked until 2FA verified.</p>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <h5 className="font-bold text-white text-xs">Administrative 8-digit Recovery Codes</h5>
                    <p className="text-[11px] text-slate-500 leading-relaxed">Save these codes. Each code can be entered once in place of OTP tokens to unlock access during disasters.</p>
                    <div className="grid grid-cols-2 gap-2 bg-slate-950 border border-white/5 p-4 rounded-xl font-mono text-center text-xs select-all">
                      {totpRecoveryCodes.map((c, i) => (
                        <span key={i} className="text-white bg-slate-900 border border-white/5 py-1 px-2.5 rounded hover:bg-slate-800">{c}</span>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB CONTENTS: OPERATIONAL SETTINGS */}
        {activeTab === 'settings' && !loading && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* ADMIN ACCOUNT SETTINGS */}
              <div className="bg-slate-900/40 border border-white/5 rounded-2xl p-6 backdrop-blur-md shadow-xl space-y-4">
                <h3 className="font-bold text-white text-sm uppercase tracking-wider border-b border-white/5 pb-2.5 flex items-center gap-2">
                  <Settings className="h-4 w-4 text-violet-400" />
                  <span>Administrative Profile Settings</span>
                </h3>
                
                <div className="space-y-4">
                  <div>
                    <h4 className="text-xs font-bold text-white uppercase tracking-wider mb-2">Change administrative username/email</h4>
                    <form onSubmit={async (e) => {
                      e.preventDefault();
                      setActionLoading(true);
                      setError('');
                      setSuccessMsg('');
                      try {
                        const res = await api.admin.changeUsername({ new_username: newEmail });
                        setAdminEmail(newEmail);
                        setSuccessMsg(res.message || 'Username updated successfully!');
                      } catch (err: any) {
                        setError(err.message || 'Username update failed.');
                      } finally {
                        setActionLoading(false);
                      }
                    }} className="space-y-3">
                      <div>
                        <input
                          type="email"
                          required
                          value={newEmail}
                          onChange={(e) => setNewEmail(e.target.value)}
                          className="w-full bg-slate-950/60 border border-white/5 rounded-xl p-3.5 text-xs text-white focus:outline-none focus:border-violet-500/50 font-mono"
                        />
                      </div>
                      <button
                        type="submit"
                        disabled={actionLoading}
                        className="px-4 py-2.5 bg-violet-600 hover:bg-violet-500 text-white font-bold text-xs rounded-xl shadow-md transition-all"
                      >
                        Update Username
                      </button>
                    </form>
                  </div>
                  
                  <div className="border-t border-white/5 pt-4 space-y-4">
                    <h4 className="text-xs font-bold text-white uppercase tracking-wider">Rotate administrative password</h4>
                    <form onSubmit={async (e) => {
                      e.preventDefault();
                      const form = e.currentTarget;
                      const pw = (form.elements.namedItem('new_password') as HTMLInputElement).value;
                      const confirm = (form.elements.namedItem('confirm_password') as HTMLInputElement).value;
                      if (!pw || pw.length < 8) {
                        setError('Password must be at least 8 characters.');
                        return;
                      }
                      if (pw !== confirm) {
                        setError('Passwords do not match.');
                        return;
                      }
                      setActionLoading(true);
                      setError('');
                      setSuccessMsg('');
                      try {
                        const res = await api.admin.changePassword({ new_password: pw });
                        setSuccessMsg('Administrative passcode rotated successfully!');
                        form.reset();
                      } catch (err: any) {
                        setError(err.message || 'Rotation failed.');
                      } finally {
                        setActionLoading(false);
                      }
                    }} className="space-y-4">
                      <div>
                        <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">New Password</label>
                        <input
                          type="password"
                          name="new_password"
                          placeholder="••••••••••••"
                          className="w-full bg-slate-950/60 border border-white/5 rounded-xl p-3.5 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-violet-500/50"
                        />
                      </div>
                      <div>
                        <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">Confirm New Password</label>
                        <input
                          type="password"
                          name="confirm_password"
                          placeholder="••••••••••••"
                          className="w-full bg-slate-950/60 border border-white/5 rounded-xl p-3.5 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-violet-500/50"
                        />
                      </div>
                      <button
                        type="submit"
                        disabled={actionLoading}
                        className="px-4 py-2.5 bg-violet-600 hover:bg-violet-500 text-white font-bold text-xs rounded-xl shadow-md transition-all"
                      >
                        Rotate Password
                      </button>
                    </form>
                  </div>
                </div>
              </div>

              {/* DUAL 2FA LOCK CONTROL */}
              <div className="bg-slate-900/40 border border-white/5 rounded-2xl p-6 backdrop-blur-md shadow-xl space-y-4">
                <h3 className="font-bold text-white text-sm uppercase tracking-wider border-b border-white/5 pb-2.5 flex items-center gap-2">
                  <Shield className="h-4 w-4 text-emerald-400" />
                  <span>Two-Factor Authentication (2FA) Status</span>
                </h3>
                
                <div className="space-y-4">
                  <div className="flex items-center justify-between p-4 bg-slate-950/60 border border-white/5 rounded-xl">
                    <div>
                      <span className="text-xs font-bold text-white block">Multi-Factor Authentication</span>
                      <span className="text-[10px] text-slate-400 mt-0.5 block">Protects normal administrative credential entries</span>
                    </div>
                    <div>
                      <span className={`text-[10px] font-bold uppercase px-2.5 py-1 rounded-full border ${totpSetupStep === 'locked' ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20' : 'text-slate-400 bg-slate-500/10 border-slate-500/20'}`}>
                        {totpSetupStep === 'locked' ? 'ACTIVE' : 'INACTIVE'}
                      </span>
                    </div>
                  </div>

                  {totpSetupStep !== 'locked' ? (
                    <div className="p-4 bg-slate-950/40 border border-dashed border-white/10 rounded-xl text-center py-6">
                      <p className="text-xs text-slate-400 mb-4 leading-relaxed">Ensure administrative safety by enforcing drifts-tolerant 2FA authentication locks.</p>
                      <button
                        onClick={() => setActiveTab('security')}
                        className="px-4 py-2.5 bg-violet-600 hover:bg-violet-500 text-white font-bold text-xs rounded-xl transition-all"
                      >
                        Configure 2FA settings now
                      </button>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      <div className="p-4 bg-emerald-950/40 border border-emerald-500/20 text-emerald-300 rounded-xl text-xs">
                        2FA is active. Keep your recovery codes safe in case you lose access.
                      </div>
                      
                      <div className="grid grid-cols-2 gap-2 bg-slate-950 border border-white/5 p-4 rounded-xl font-mono text-center text-[10px] select-all">
                        {totpRecoveryCodes.map((c, i) => (
                          <span key={i} className="text-white bg-slate-900 border border-white/5 py-1 px-2 rounded hover:bg-slate-800">{c}</span>
                        ))}
                      </div>

                      <button
                        onClick={async () => {
                          if (!confirm('Are you sure you want to disable 2FA? This lowers your security boundary.')) return;
                          setActionLoading(true);
                          setError('');
                          setSuccessMsg('');
                          try {
                            const res = await api.admin.totpDisable();
                            setTotpSetupStep('idle');
                            setTotpSecret('');
                            setTotpQr('');
                            setTotpVerifyCode('');
                            setTotpRecoveryCodes([]);
                            setSuccessMsg(res.message || '2FA has been successfully deactivated.');
                          } catch (err: any) {
                            setError(err.message || 'Failed to deactivate 2FA.');
                          } finally {
                            setActionLoading(false);
                          }
                        }}
                        className="w-full py-2.5 bg-rose-600/10 hover:bg-rose-600/20 border border-rose-500/20 hover:border-rose-500/40 text-rose-300 font-bold text-xs rounded-xl transition-all"
                      >
                        Deactivate 2FA locks
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* NOTIFICATION PREFERENCES & AUDIT SETTINGS */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="bg-slate-900/40 border border-white/5 rounded-2xl p-6 backdrop-blur-md shadow-xl space-y-4">
                <h3 className="font-bold text-white text-sm uppercase tracking-wider border-b border-white/5 pb-2.5 flex items-center gap-2">
                  <Activity className="h-4 w-4 text-sky-400" />
                  <span>Notification Preferences</span>
                </h3>
                
                <div className="space-y-4 text-xs text-slate-400">
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="font-semibold text-white block">Email Alerts on Suspension</span>
                      <p className="text-[10px] text-slate-500 mt-0.5">Alert administrative mailbox when a tenant is terminated or suspended.</p>
                    </div>
                    <input type="checkbox" defaultChecked className="h-4 w-4 rounded border-white/5 bg-slate-950 accent-violet-600" />
                  </div>
                  <div className="flex items-center justify-between border-t border-white/5 pt-4">
                    <div>
                      <span className="font-semibold text-white block">Real-time Sockets Broadcasts</span>
                      <p className="text-[10px] text-slate-500 mt-0.5">Stream live audit logs directly to this control board panel.</p>
                    </div>
                    <input type="checkbox" defaultChecked className="h-4 w-4 rounded border-white/5 bg-slate-950 accent-violet-600" />
                  </div>
                </div>
              </div>

              <div className="bg-slate-900/40 border border-white/5 rounded-2xl p-6 backdrop-blur-md shadow-xl space-y-4">
                <h3 className="font-bold text-white text-sm uppercase tracking-wider border-b border-white/5 pb-2.5 flex items-center gap-2">
                  <Terminal className="h-4 w-4 text-pink-400" />
                  <span>Audit Settings & telemetry parameters</span>
                </h3>
                
                <div className="space-y-4 text-xs text-slate-400">
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="font-semibold text-white block">Log Administrative Actions</span>
                      <p className="text-[10px] text-slate-500 mt-0.5">Track old and new states permanently in PostgreSQL database.</p>
                    </div>
                    <input type="checkbox" defaultChecked disabled className="h-4 w-4 rounded border-white/5 bg-slate-950 accent-violet-600 cursor-not-allowed opacity-50" />
                  </div>
                  <div className="flex items-center justify-between border-t border-white/5 pt-4">
                    <div>
                      <span className="font-semibold text-white block">Anonymize Suspended Data logs</span>
                      <p className="text-[10px] text-slate-500 mt-0.5">Anonymize customer identity parameters on hard termination purges.</p>
                    </div>
                    <input type="checkbox" defaultChecked className="h-4 w-4 rounded border-white/5 bg-slate-950 accent-violet-600" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* ALL CONTROLS MODALS */}
      {modalType && activeTenant && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-md bg-slate-900 border border-white/5 rounded-2xl p-6 relative shadow-2xl animate-scaleUp">
            <h4 className="font-bold text-white tracking-wide text-base mb-4 uppercase">
              {modalType === 'plan' && `Modify Subscription - ${activeTenant.name}`}
              {modalType === 'quota' && `Quota Override - ${activeTenant.name}`}
              {modalType === 'terminate' && `Service Termination - ${activeTenant.name}`}
            </h4>

            <form onSubmit={handleModalSubmit} className="space-y-4">
              {/* MODAL PHASE: PLAN OVERRIDE */}
              {modalType === 'plan' && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">Select Tier Plan</label>
                    <select
                      value={planForm.plan_tier}
                      onChange={(e) => setPlanForm({ ...planForm, plan_tier: e.target.value })}
                      className="w-full bg-slate-950 border border-white/5 rounded-xl p-3 text-xs text-white uppercase focus:outline-none"
                    >
                      <option value="free">Free Trial</option>
                      <option value="starter">Starter Plan</option>
                      <option value="pro">Pro Plan</option>
                      <option value="agency">Agency / Enterprise Plan</option>
                    </select>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">Max Bots</label>
                      <input
                        type="number"
                        value={planForm.max_bots}
                        onChange={(e) => setPlanForm({ ...planForm, max_bots: parseInt(e.target.value) })}
                        className="w-full bg-slate-950 border border-white/5 rounded-xl p-3 text-xs text-white focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">Max Messages</label>
                      <input
                        type="number"
                        value={planForm.max_messages}
                        onChange={(e) => setPlanForm({ ...planForm, max_messages: parseInt(e.target.value) })}
                        className="w-full bg-slate-950 border border-white/5 rounded-xl p-3 text-xs text-white focus:outline-none"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">Extend/Reduce period (Days offset)</label>
                    <input
                      type="number"
                      value={planForm.days}
                      onChange={(e) => setPlanForm({ ...planForm, days: parseInt(e.target.value) })}
                      className="w-full bg-slate-950 border border-white/5 rounded-xl p-3 text-xs text-white focus:outline-none"
                    />
                  </div>
                </div>
              )}

              {/* MODAL PHASE: QUOTA OVERRIDE */}
              {modalType === 'quota' && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">Custom Max Bots</label>
                    <input
                      type="number"
                      value={quotaForm.max_bots}
                      onChange={(e) => setQuotaForm({ ...quotaForm, max_bots: parseInt(e.target.value) })}
                      className="w-full bg-slate-950 border border-white/5 rounded-xl p-3 text-xs text-white focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">Custom Max Messages</label>
                    <input
                      type="number"
                      value={quotaForm.max_messages}
                      onChange={(e) => setQuotaForm({ ...quotaForm, max_messages: parseInt(e.target.value) })}
                      className="w-full bg-slate-950 border border-white/5 rounded-xl p-3 text-xs text-white focus:outline-none"
                    />
                  </div>
                </div>
              )}

              {/* MODAL PHASE: SERVICE TERMINATION */}
              {modalType === 'terminate' && (
                <div className="space-y-4">
                  <div className="p-3.5 bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs rounded-xl flex gap-2">
                    <AlertOctagon className="h-5 w-5 text-rose-400 shrink-0 mt-0.5" />
                    <div>
                      <span className="font-bold block mb-1">Extremely High Risk Operation</span>
                      <p className="text-[10px] text-slate-400 leading-relaxed">
                        Specify termination severity. Instant shuts logins and disconnects channels immediately. Graceful grants 24 hours of warn banners and settling times.
                      </p>
                    </div>
                  </div>

                  <div className="flex gap-4">
                    <label className="flex items-center gap-2 text-xs font-semibold cursor-pointer">
                      <input
                        type="radio"
                        checked={terminateMode === 'graceful'}
                        onChange={() => setTerminateMode('graceful')}
                        className="accent-violet-500 h-4 w-4"
                      />
                      <span>Mode 2: Graceful Termination (24h grace)</span>
                    </label>
                  </div>
                  
                  <div className="flex gap-4">
                    <label className="flex items-center gap-2 text-xs font-semibold cursor-pointer">
                      <input
                        type="radio"
                        checked={terminateMode === 'instant'}
                        onChange={() => setTerminateMode('instant')}
                        className="accent-violet-500 h-4 w-4"
                      />
                      <span className="text-rose-400 font-bold">Mode 1: Instant Absolute Shutdown</span>
                    </label>
                  </div>
                </div>
              )}

              <div className="flex justify-end gap-3 pt-4 border-t border-white/5">
                <button
                  type="button"
                  onClick={() => setModalType(null)}
                  className="px-4 py-2 bg-slate-950 border border-white/5 hover:bg-slate-800 text-slate-400 hover:text-white rounded-xl text-xs font-bold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className={`px-4 py-2 text-white rounded-xl text-xs font-bold shadow-md transition-all ${
                    modalType === 'terminate' 
                      ? 'bg-rose-600 hover:bg-rose-500' 
                      : 'bg-violet-600 hover:bg-violet-500'
                  }`}
                >
                  {actionLoading ? 'Saving...' : 'Lock In Action'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
