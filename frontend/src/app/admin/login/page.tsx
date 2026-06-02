'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { Lock, Mail, ShieldAlert, Sparkles, Key, ArrowRight, ShieldCheck } from 'lucide-react';

export default function AdminLoginPage() {
  const router = useRouter();
  
  // Auth phase control: 'credentials' | 'change_password' | 'totp'
  const [phase, setPhase] = useState<'credentials' | 'change_password' | 'totp'>('credentials');
  
  // Credentials States
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  
  // Password Change States
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  
  // TOTP States
  const [totpCode, setTotpCode] = useState('');
  
  // General Page States
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [tempToken, setTempToken] = useState('');

  // Handle email/password credentials phase
  const handleCredentialsSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) return;
    
    setError('');
    setLoading(true);
    try {
      const res = await api.admin.login({ email, password });
      
      // Store temp token in localStorage so subsequent API calls use it
      localStorage.setItem('replyos_admin_token', res.access_token);
      setTempToken(res.access_token);
      
      if (res.must_change_password) {
        localStorage.setItem('replyos_admin_tenant_id', res.tenant_id || '');
        setPhase('change_password');
      } else if (res.totp_enabled) {
        localStorage.setItem('replyos_admin_tenant_id', res.tenant_id || '');
        setPhase('totp');
      } else {
        // Normal successful login (no password change, no 2FA)
        api.setSession(res.access_token, res.tenant_id, 'admin');
        router.push('/admin');
      }
    } catch (err: any) {
      setError(err.message || 'Login failed. Please verify credentials.');
      localStorage.removeItem('replyos_admin_token');
    } finally {
      setLoading(false);
    }
  };


  // Handle first-time password rotation phase
  const handleChangePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newPassword || !confirmPassword) return;
    
    if (newPassword.length < 8) {
      setError('Password must be at least 8 characters long.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }
    
    setError('');
    setLoading(true);
    try {
      const res = await api.admin.changePassword({ new_password: newPassword });
      
      // Update token in localStorage
      localStorage.setItem('replyos_admin_token', res.access_token);
      setTempToken(res.access_token);
      
      if (res.totp_enabled) {
        setPhase('totp');
      } else {
        // Fully authenticated!
        api.setSession(res.access_token, res.tenant_id || '', 'admin');
        router.push('/admin');
      }
    } catch (err: any) {
      setError(err.message || 'Password update failed.');
    } finally {
      setLoading(false);
    }
  };

  // Handle 2FA TOTP phase
  const handleTotpVerifySubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!totpCode) return;
    
    setError('');
    setLoading(true);
    try {
      const res = await api.admin.totpVerify({ code: totpCode });
      
      // Fully authenticated!
      api.setSession(res.access_token, res.tenant_id, 'admin');
      router.push('/admin');
    } catch (err: any) {
      setError(err.message || 'Invalid 2FA code. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen bg-slate-950 relative overflow-hidden px-4">
      {/* Dynamic Animated Glow Backdrops */}
      <div className="absolute top-[-15%] left-[-15%] w-[60%] h-[60%] bg-violet-600/10 rounded-full blur-[160px] pointer-events-none animate-pulse duration-10000"></div>
      <div className="absolute bottom-[-15%] right-[-15%] w-[60%] h-[60%] bg-rose-600/10 rounded-full blur-[160px] pointer-events-none animate-pulse duration-10000"></div>

      <div className="w-full max-w-md bg-slate-900/60 backdrop-blur-2xl border border-white/5 p-8 rounded-2xl shadow-2xl relative">
        <div className="absolute -top-px left-10 right-10 h-[2px] bg-gradient-to-r from-transparent via-violet-500 to-transparent"></div>
        
        {/* Brand Header */}
        <div className="flex flex-col items-center mb-8">
          <div className="h-14 w-14 rounded-2xl bg-gradient-to-tr from-violet-600 to-pink-500 flex items-center justify-center shadow-lg shadow-violet-500/20 mb-3 border border-white/10 relative group">
            <ShieldCheck className="h-7 w-7 text-white" />
            <div className="absolute inset-0 rounded-2xl bg-violet-500/20 blur opacity-0 group-hover:opacity-100 transition-opacity"></div>
          </div>
          <h2 className="text-2xl font-bold tracking-tight text-white bg-clip-text bg-gradient-to-b from-white to-slate-300">ReplyOS Control Plane</h2>
          <p className="text-xs font-medium text-violet-400/80 uppercase tracking-widest mt-1">SaaS Owner Operations</p>
        </div>

        {/* Error Notification Banner */}
        {error && (
          <div className="mb-6 p-4 bg-rose-950/40 border border-rose-500/30 text-rose-300 rounded-xl text-xs flex items-start gap-3 animate-shake">
            <ShieldAlert className="h-5 w-5 mt-0.5 shrink-0 text-rose-400" />
            <div className="flex-1">
              <span className="font-semibold block mb-0.5">Security Notice</span>
              <span>{error}</span>
            </div>
          </div>
        )}

        {/* PHASE 1: CREDENTIALS */}
        {phase === 'credentials' && (
          <form onSubmit={handleCredentialsSubmit} className="space-y-5">
            <div>
              <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">Master Administrator Email</label>
              <div className="relative">
                <Mail className="absolute left-3.5 top-3.5 h-4.5 w-4.5 text-slate-500" />
                <input
                  type="email"
                  value={email}
                  required
                  placeholder="admin@replyos.com"
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full bg-slate-950/60 border border-white/5 rounded-xl py-3.5 pl-11 pr-4 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-violet-500/50 focus:ring-1 focus:ring-violet-500/20 transition-all"
                />
              </div>
            </div>

            <div>
              <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">Secure Passcode</label>
              <div className="relative">
                <Lock className="absolute left-3.5 top-3.5 h-4.5 w-4.5 text-slate-500" />
                <input
                  type="password"
                  value={password}
                  required
                  placeholder="••••••••••••"
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-slate-950/60 border border-white/5 rounded-xl py-3.5 pl-11 pr-4 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-violet-500/50 focus:ring-1 focus:ring-violet-500/20 transition-all"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white font-medium text-sm py-3.5 rounded-xl shadow-lg shadow-violet-600/20 flex items-center justify-center gap-2 transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed group mt-2"
            >
              {loading ? (
                <div className="h-5 w-5 border-2 border-white/20 border-t-white rounded-full animate-spin"></div>
              ) : (
                <>
                  <span>Unlock Administrative Plane</span>
                  <ArrowRight className="h-4 w-4 group-hover:translate-x-1 transition-transform" />
                </>
              )}
            </button>

          </form>
        )}

        {/* PHASE 2: FORCED PASSWORD ROTATION */}
        {phase === 'change_password' && (
          <form onSubmit={handleChangePasswordSubmit} className="space-y-5">
            <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl mb-4">
              <span className="text-amber-400 text-xs font-semibold block mb-0.5">First Login Required Step</span>
              <p className="text-[11px] text-amber-300/80 leading-relaxed">
                Security compliance rules dictate that you must rotate your temporary password on your first authentication event.
              </p>
            </div>

            <div>
              <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">New Password</label>
              <div className="relative">
                <Key className="absolute left-3.5 top-3.5 h-4.5 w-4.5 text-slate-500" />
                <input
                  type="password"
                  value={newPassword}
                  required
                  placeholder="••••••••"
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="w-full bg-slate-950/60 border border-white/5 rounded-xl py-3.5 pl-11 pr-4 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-violet-500/50 focus:ring-1 focus:ring-violet-500/20 transition-all"
                />
              </div>
            </div>

            <div>
              <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">Confirm New Password</label>
              <div className="relative">
                <Key className="absolute left-3.5 top-3.5 h-4.5 w-4.5 text-slate-500" />
                <input
                  type="password"
                  value={confirmPassword}
                  required
                  placeholder="••••••••"
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="w-full bg-slate-950/60 border border-white/5 rounded-xl py-3.5 pl-11 pr-4 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-violet-500/50 focus:ring-1 focus:ring-violet-500/20 transition-all"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 text-white font-medium text-sm py-3.5 rounded-xl shadow-lg shadow-amber-500/20 flex items-center justify-center gap-2 transition-all duration-300 disabled:opacity-50"
            >
              {loading ? (
                <div className="h-5 w-5 border-2 border-white/20 border-t-white rounded-full animate-spin"></div>
              ) : (
                <span>Lock In New Credentials</span>
              )}
            </button>
          </form>
        )}

        {/* PHASE 3: TOTP 2FA CHALLENGE */}
        {phase === 'totp' && (
          <form onSubmit={handleTotpVerifySubmit} className="space-y-5">
            <div className="p-3 bg-violet-500/10 border border-violet-500/20 rounded-xl mb-4">
              <span className="text-violet-400 text-xs font-semibold block mb-0.5">Two-Factor Authentication</span>
              <p className="text-[11px] text-violet-300/80 leading-relaxed">
                Enter the 6-digit verification code from your authenticator app or one of your secure recovery codes.
              </p>
            </div>

            <div>
              <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">2FA Security Token / Recovery Code</label>
              <div className="relative">
                <Lock className="absolute left-3.5 top-3.5 h-4.5 w-4.5 text-slate-500" />
                <input
                  type="text"
                  value={totpCode}
                  required
                  placeholder="000 000"
                  maxLength={12}
                  onChange={(e) => setTotpCode(e.target.value)}
                  className="w-full bg-slate-950/60 border border-white/5 rounded-xl py-3.5 pl-11 pr-4 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-violet-500/50 focus:ring-1 focus:ring-violet-500/20 transition-all tracking-widest text-center font-mono text-base"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white font-medium text-sm py-3.5 rounded-xl shadow-lg shadow-violet-600/20 flex items-center justify-center gap-2 transition-all duration-300 disabled:opacity-50"
            >
              {loading ? (
                <div className="h-5 w-5 border-2 border-white/20 border-t-white rounded-full animate-spin"></div>
              ) : (
                <span>Verify Token & Unlock</span>
              )}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
