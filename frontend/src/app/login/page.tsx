'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { Lock, Mail, Users, ArrowRight, ShieldAlert, Sparkles } from 'lucide-react';

export default function LoginPage() {
  const router = useRouter();
  const [isLogin, setIsLogin] = useState(true);
  
  // Login Form States
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  
  // Register Form States
  const [regEmail, setRegEmail] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [tenantName, setTenantName] = useState('');
  const [subdomain, setSubdomain] = useState('');
  
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await api.auth.login({ email, password });
      api.setSession(res.access_token, res.tenant_id, res.role);
      router.push('/dashboard');
    } catch (err: any) {
      setError(err.message || 'Login failed.');
    } finally {
      setLoading(false);
    }
  };


  const handleRegisterSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await api.auth.register({
        email: regEmail,
        password: regPassword,
        first_name: firstName || undefined,
        last_name: lastName || undefined,
        tenant_name: tenantName,
        subdomain: subdomain || undefined
      });
      api.setSession(res.access_token, res.tenant_id, res.role);
      router.push('/dashboard');
    } catch (err: any) {
      setError(err.message || 'Registration failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen bg-background relative overflow-hidden px-4">
      {/* Decorative Glow Elements */}
      <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-primary/20 rounded-full blur-[150px] pointer-events-none"></div>
      <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] bg-accent/15 rounded-full blur-[150px] pointer-events-none"></div>

      <div className="w-full max-w-md bg-card/60 backdrop-blur-xl border border-white/5 p-8 rounded-2xl shadow-2xl relative">
        
        {/* Brand Logo Header */}
        <div className="flex flex-col items-center mb-8">
          <div className="h-12 w-12 rounded-xl bg-gradient-to-tr from-primary to-violet-500 flex items-center justify-center shadow-lg shadow-primary/30 mb-3">
            <Sparkles className="h-6 w-6 text-white animate-pulse" />
          </div>
          <h2 className="text-2xl font-bold tracking-tight text-white">ReplyOS</h2>
          <p className="text-xs text-slate-400 mt-1">Multi-Tenant WhatsApp AI SaaS Platform</p>
        </div>

        {/* Error message badge */}
        {error && (
          <div className="mb-6 p-3.5 bg-red-950/40 border border-red-500/20 text-red-400 rounded-lg text-xs flex items-start gap-2.5">
            <ShieldAlert className="h-4.5 w-4.5 mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {isLogin ? (
          /* LOGIN FORM */
          <form onSubmit={handleLoginSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">Email Address</label>
              <div className="relative">
                <Mail className="absolute left-3 top-3 h-4 w-4 text-slate-500" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2.5 pl-10 pr-4 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/20"
                  placeholder="name@company.com"
                  required
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">Password</label>
              <div className="relative">
                <Lock className="absolute left-3 top-3 h-4 w-4 text-slate-500" />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2.5 pl-10 pr-4 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/20"
                  placeholder="••••••••"
                  required
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-primary hover:bg-primary-hover text-white rounded-lg py-2.5 font-medium text-sm flex items-center justify-center gap-2 mt-6 transition shadow-md shadow-primary/25 disabled:opacity-50 disabled:pointer-events-none"
            >
              {loading ? 'Validating credentials...' : 'Enter Console'}
              <ArrowRight className="h-4 w-4" />
            </button>


            <div className="text-center mt-6">
              <span className="text-xs text-slate-400">New to the platform? </span>
              <button
                type="button"
                onClick={() => { setIsLogin(false); setError(''); }}
                className="text-xs text-primary hover:underline font-semibold"
              >
                Create Tenant Space
              </button>
            </div>
          </form>
        ) : (
          /* REGISTRATION FORM */
          <form onSubmit={handleRegisterSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">First Name</label>
                <input
                  type="text"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2.5 px-4 text-sm text-white focus:outline-none focus:border-primary/50"
                  placeholder="John"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">Last Name</label>
                <input
                  type="text"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2.5 px-4 text-sm text-white focus:outline-none focus:border-primary/50"
                  placeholder="Doe"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">Company Name (Tenant)</label>
              <div className="relative">
                <Users className="absolute left-3 top-3 h-4 w-4 text-slate-500" />
                <input
                  type="text"
                  value={tenantName}
                  onChange={(e) => setTenantName(e.target.value)}
                  className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2.5 pl-10 pr-4 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-primary/50"
                  placeholder="Acme Inc."
                  required
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">Subdomain</label>
                <input
                  type="text"
                  value={subdomain}
                  onChange={(e) => setSubdomain(e.target.value)}
                  className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2.5 px-4 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-primary/50"
                  placeholder="acme"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">Account Email</label>
                <input
                  type="email"
                  value={regEmail}
                  onChange={(e) => setRegEmail(e.target.value)}
                  className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2.5 px-4 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-primary/50"
                  placeholder="john@acme.com"
                  required
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">Create Password</label>
              <input
                type="password"
                value={regPassword}
                onChange={(e) => setRegPassword(e.target.value)}
                className="w-full bg-slate-950/50 border border-white/5 rounded-lg py-2.5 px-4 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-primary/50"
                placeholder="••••••••"
                required
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-primary hover:bg-primary-hover text-white rounded-lg py-2.5 font-medium text-sm flex items-center justify-center gap-2 mt-6 transition shadow-md shadow-primary/25 disabled:opacity-50 disabled:pointer-events-none"
            >
              {loading ? 'Creating Tenant space...' : 'Provision Space'}
              <ArrowRight className="h-4 w-4" />
            </button>

            <div className="text-center mt-6">
              <span className="text-xs text-slate-400">Already registered? </span>
              <button
                type="button"
                onClick={() => { setIsLogin(true); setError(''); }}
                className="text-xs text-primary hover:underline font-semibold"
              >
                Access Console
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
