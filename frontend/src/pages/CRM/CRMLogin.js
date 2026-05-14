import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Eye, EyeOff, ArrowRight, ArrowLeft, Check, Users, Building2, CreditCard, Loader2, Shield } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const PLANS = {
  starter: {
    name: 'Starter', base: 9.99, perUser: 4.99, color: 'var(--color-info-ios)',
    features: ['Contact & Company Management', 'Basic Deal Pipeline', 'Email Integration', 'Activity Tracking', 'Mobile Access'],
    best: false,
  },
  professional: {
    name: 'Professional', base: 19.99, perUser: 9.99, color: 'var(--color-success-alt)',
    features: ['Everything in Starter', 'AI-Powered Insights', 'Custom Pipelines', 'Workflow Automation', 'Quote & Proposal Builder', 'Advanced Reporting', 'Team Collaboration'],
    best: true,
  },
  enterprise: {
    name: 'Enterprise', base: 29.99, perUser: 14.99, color: 'var(--color-accent-magenta)',
    features: ['Everything in Professional', 'Custom Integrations (API)', 'White-Label Branding', 'Advanced Security & SSO', 'Unlimited Workflows', 'Priority Support', 'Data Import/Export Tools'],
    best: false,
  },
};

export default function CRMLogin({ onLogin }) {
  const [mode, setMode] = useState('login'); // login | signup
  const [step, setStep] = useState(1); // 1=plan, 2=details, 3=confirm
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [fullName, setFullName] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [selectedPlan, setSelectedPlan] = useState('professional');
  const [teamSize, setTeamSize] = useState(1);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [needs2FA, setNeeds2FA] = useState(false);
  const [tempToken, setTempToken] = useState('');
  const [twoFACode, setTwoFACode] = useState('');
  const [twoFAUser, setTwoFAUser] = useState(null);

  const theme = localStorage.getItem('theme') || 'dark';

  // Clear any stale CRM token when on login page
  useEffect(() => {
    localStorage.removeItem('crm_token');
  }, []);
  const isDark = theme === 'dark';
  const bg = isDark ? 'var(--color-ink-alt)' : 'var(--color-neutral-25)';
  const surface = isDark ? 'var(--color-neutral-900)' : 'var(--color-white)';
  const border = isDark ? 'var(--color-surface-dark-3)' : 'var(--color-border-alt)';
  const txt = isDark ? 'var(--color-neutral-50)' : '#111827';
  const txtM = isDark ? 'var(--color-neutral-400)' : 'var(--color-text-faint-alt)';
  const inputBg = isDark ? 'var(--color-ink-alt)' : 'var(--color-white)';

  // Iter 216h101 — branding leak fix. The CRM is shared across GymAxis
  // and Pulse Fitness deployments. Default brand label tracks the host
  // domain so a Pulse Fitness operator never sees "GymAxis CRM" on the
  // login screen, and vice versa.
  const isPulseHost = typeof window !== 'undefined' && /pulsefitness|pulse-fitness|pulse\.local/i.test(window.location.hostname || '');
  const brandLabel = isPulseHost ? 'Pulse Fitness CRM' : 'GymAxis CRM';
  const brandInitial = isPulseHost ? 'P' : 'G';

  const plan = PLANS[selectedPlan];
  const monthlyTotal = plan ? (plan.base + plan.perUser * teamSize).toFixed(2) : '0.00';

  const handleLogin = async (e) => {
    e.preventDefault();
    setError(''); setLoading(true);
    try {
      const { data } = await axios.post(`${API}/crm/auth/login`, { email, password });
      if (data.requires_2fa) {
        setNeeds2FA(true);
        setTempToken(data.temp_token);
        setTwoFAUser(data.user);
        setTwoFACode('');
      } else {
        onLogin(data.token, data.user);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Invalid credentials');
    } finally { setLoading(false); }
  };

  const handle2FAVerify = async (e) => {
    e.preventDefault();
    setError(''); setLoading(true);
    try {
      const { data } = await axios.post(`${API}/crm/auth/2fa/validate`, { temp_token: tempToken, code: twoFACode });
      onLogin(data.token, data.user);
    } catch (err) {
      setError(err.response?.data?.detail || 'Invalid 2FA code');
    } finally { setLoading(false); }
  };

  const handleRegister = async () => {
    setError(''); setLoading(true);
    try {
      const { data } = await axios.post(`${API}/crm/auth/register`, {
        email, password, full_name: fullName,
        company_name: companyName, plan: selectedPlan, team_size: teamSize,
      });
      onLogin(data.token, data.user);
    } catch (err) {
      setError(err.response?.data?.detail || 'Registration failed');
    } finally { setLoading(false); }
  };

  const canProceedStep2 = fullName && email && password && password.length >= 6 && companyName;

  if (mode === 'login') {
    // 2FA Verification Screen
    if (needs2FA) {
      return (
        <div className="min-h-screen flex items-center justify-center px-4" style={{ background: bg }}>
          <div className="w-full max-w-sm" data-testid="crm-2fa-page">
            <div className="flex items-center gap-3 mb-8">
              <div className="w-10 h-10 rounded-lg bg-[var(--color-info-ios)] flex items-center justify-center text-white font-bold text-lg">{brandInitial}</div>
              <span className="text-xl font-semibold tracking-tight" style={{ color: txt }}>{brandLabel}</span>
            </div>
            <div className="w-12 h-12 rounded-full bg-[rgb(var(--rgb-info-ios)/0.1)] flex items-center justify-center mx-auto mb-4">
              <Shield size={24} style={{ color: 'var(--color-info-ios)' }} />
            </div>
            <h2 className="text-2xl font-semibold mb-1 text-center" style={{ color: txt }}>Two-Factor Authentication</h2>
            <p className="text-sm mb-6 text-center" style={{ color: txtM }}>
              Enter the 6-digit code from your authenticator app{twoFAUser?.full_name ? `, ${twoFAUser.full_name}` : ''}
            </p>
            {error && <div className="mb-4 px-4 py-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-500 text-sm" data-testid="crm-2fa-error">{error}</div>}
            <form onSubmit={handle2FAVerify} className="space-y-4">
              <div>
                <label className="block text-xs mb-1.5 uppercase tracking-wider font-medium" style={{ color: txtM }}>Verification Code</label>
                <input
                  type="text"
                  value={twoFACode}
                  onChange={e => setTwoFACode(e.target.value.replace(/\D/g, '').slice(0, 8))}
                  className="w-full px-4 py-3 text-lg font-mono text-center tracking-[0.4em] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--color-info-ios)]"
                  style={{ background: inputBg, border: `1px solid ${border}`, color: txt }}
                  placeholder="000000"
                  autoFocus
                  required
                  data-testid="crm-2fa-code"
                />
                <p className="text-[11px] mt-2 text-center" style={{ color: txtM }}>Enter your 6-digit code or a backup code</p>
              </div>
              <button type="submit" disabled={loading || twoFACode.length < 6} className="w-full py-3 bg-[var(--color-info-ios)] text-white text-sm font-semibold rounded-lg disabled:opacity-50 flex items-center justify-center gap-2" data-testid="crm-2fa-submit">
                {loading ? <Loader2 size={16} className="animate-spin" /> : <Shield size={16} />}
                {loading ? 'Verifying...' : 'Verify'}
              </button>
              <button type="button" onClick={() => { setNeeds2FA(false); setTempToken(''); setTwoFACode(''); setError(''); }}
                className="w-full text-sm text-center hover:underline" style={{ color: txtM }}>
                Back to login
              </button>
            </form>
          </div>
        </div>
      );
    }

    return (
      <div className="min-h-screen flex items-center justify-center px-4" style={{ background: bg }}>
        <div className="w-full max-w-sm" data-testid="crm-login-page">
          <div className="flex items-center gap-3 mb-8">
            <div className="w-10 h-10 rounded-lg bg-[var(--color-info-ios)] flex items-center justify-center text-white font-bold text-lg">{brandInitial}</div>
            <span className="text-xl font-semibold tracking-tight" style={{ color: txt }}>{brandLabel}</span>
          </div>
          <h2 className="text-2xl font-semibold mb-1" style={{ color: txt }}>Welcome back</h2>
          <p className="text-sm mb-6" style={{ color: txtM }}>Sign in to your CRM account</p>
          {error && <div className="mb-4 px-4 py-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-500 text-sm" data-testid="crm-login-error">{error}</div>}
          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-xs mb-1.5 uppercase tracking-wider font-medium" style={{ color: txtM }}>Email</label>
              <input type="email" value={email} onChange={e => setEmail(e.target.value)} className="w-full px-4 py-2.5 text-sm rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--color-info-ios)]" style={{ background: inputBg, border: `1px solid ${border}`, color: txt }} placeholder="you@company.com" required data-testid="crm-login-email" />
            </div>
            <div>
              <label className="block text-xs mb-1.5 uppercase tracking-wider font-medium" style={{ color: txtM }}>Password</label>
              <div className="relative">
                <input type={showPwd ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)} className="w-full px-4 py-2.5 pr-10 text-sm rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--color-info-ios)]" style={{ background: inputBg, border: `1px solid ${border}`, color: txt }} placeholder="Your password" required data-testid="crm-login-password" />
                <button type="button" onClick={() => setShowPwd(!showPwd)} className="absolute right-3 top-1/2 -translate-y-1/2" style={{ color: txtM }}>{showPwd ? <EyeOff size={16} /> : <Eye size={16} />}</button>
              </div>
            </div>
            <button type="submit" disabled={loading} className="w-full flex items-center justify-center gap-2 py-2.5 bg-[var(--color-info-ios)] hover:bg-[var(--color-brand-blue-deep)] text-white text-sm font-medium rounded-lg transition-all disabled:opacity-50" data-testid="crm-login-submit">
              {loading ? <Loader2 size={16} className="animate-spin" /> : <>Sign In <ArrowRight size={16} /></>}
            </button>
          </form>
          <p className="mt-6 text-center text-sm" style={{ color: txtM }}>
            Don't have an account?{' '}
            <button onClick={() => { setMode('signup'); setStep(1); setError(''); }} className="text-[var(--color-info-ios)] hover:underline font-medium" data-testid="crm-toggle-mode">Start free trial</button>
          </p>
        </div>
      </div>
    );
  }

  // SIGNUP FLOW
  return (
    <div className="min-h-screen" style={{ background: bg }}>
      {/* Header */}
      <div className="border-b px-6 py-4 flex items-center justify-between" style={{ borderColor: border, background: surface }}>
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-[var(--color-info-ios)] flex items-center justify-center text-white font-bold text-sm">{brandInitial}</div>
          <span className="text-lg font-semibold" style={{ color: txt }}>{brandLabel}</span>
        </div>
        <button onClick={() => { setMode('login'); setError(''); }} className="text-sm font-medium text-[var(--color-info-ios)] hover:underline" data-testid="back-to-login">Already have an account? Sign in</button>
      </div>

      {/* Progress */}
      <div className="max-w-3xl mx-auto px-6 pt-8">
        <div className="flex items-center justify-center gap-2 mb-8">
          {[{ n: 1, label: 'Choose Plan' }, { n: 2, label: 'Your Details' }, { n: 3, label: 'Confirm' }].map((s, i) => (
            <React.Fragment key={s.n}>
              {i > 0 && <div className="w-12 h-0.5 rounded" style={{ background: step >= s.n ? 'var(--color-info-ios)' : border }} />}
              <div className="flex items-center gap-2">
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${step >= s.n ? 'bg-[var(--color-info-ios)] text-white' : ''}`} style={step < s.n ? { background: isDark ? 'var(--color-surface-dark-3)' : 'var(--color-border-alt)', color: txtM } : {}}>
                  {step > s.n ? <Check size={14} /> : s.n}
                </div>
                <span className="text-xs font-medium hidden sm:inline" style={{ color: step >= s.n ? txt : txtM }}>{s.label}</span>
              </div>
            </React.Fragment>
          ))}
        </div>

        {error && <div className="mb-4 px-4 py-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-500 text-sm">{error}</div>}

        {/* Step 1: Plan Selection */}
        {step === 1 && (
          <div data-testid="signup-step-plan">
            <h2 className="text-2xl font-semibold text-center mb-2" style={{ color: txt }}>Choose your plan</h2>
            <p className="text-center mb-8 text-sm" style={{ color: txtM }}>All plans include a 14-day free trial. No credit card required.</p>
            <div className="grid md:grid-cols-3 gap-4">
              {Object.entries(PLANS).map(([key, p]) => (
                <div key={key} onClick={() => setSelectedPlan(key)}
                  className={`relative rounded-xl p-5 cursor-pointer transition-all ${selectedPlan === key ? 'ring-2 ring-[var(--color-info-ios)] scale-[1.02]' : 'hover:scale-[1.01]'}`}
                  style={{ background: surface, border: `1px solid ${selectedPlan === key ? 'var(--color-info-ios)' : border}` }}
                  data-testid={`plan-${key}`}>
                  {p.best && <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-0.5 bg-[var(--color-success-alt)] text-white text-[10px] font-bold uppercase rounded-full tracking-wider">Most Popular</div>}
                  <div className="w-10 h-10 rounded-lg flex items-center justify-center mb-3" style={{ background: `${p.color}20` }}>
                    <CreditCard size={20} style={{ color: p.color }} />
                  </div>
                  <h3 className="text-lg font-semibold mb-1" style={{ color: txt }}>{p.name}</h3>
                  <div className="mb-4">
                    <span className="text-3xl font-bold" style={{ color: txt }}>£{p.base.toFixed(2)}</span>
                    <span className="text-sm" style={{ color: txtM }}>/mo + £{p.perUser.toFixed(2)}/user</span>
                  </div>
                  <ul className="space-y-2">
                    {p.features.map(f => (
                      <li key={f} className="flex items-start gap-2 text-sm" style={{ color: txtM }}>
                        <Check size={14} className="mt-0.5 flex-shrink-0" style={{ color: p.color }} />
                        {f}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>

            {/* Team size */}
            <div className="mt-6 p-4 rounded-xl flex flex-col sm:flex-row items-center gap-4 justify-between" style={{ background: surface, border: `1px solid ${border}` }}>
              <div className="flex items-center gap-3">
                <Users size={20} style={{ color: 'var(--color-info-ios)' }} />
                <div>
                  <p className="text-sm font-medium" style={{ color: txt }}>Team Size</p>
                  <p className="text-xs" style={{ color: txtM }}>How many people will use the CRM?</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <button onClick={() => setTeamSize(Math.max(1, teamSize - 1))} className="w-8 h-8 rounded-lg flex items-center justify-center text-lg font-bold" style={{ background: isDark ? 'var(--color-surface-dark-3)' : 'var(--color-neutral-100)', color: txt }}>-</button>
                <span className="text-xl font-bold w-8 text-center" style={{ color: txt }}>{teamSize}</span>
                <button onClick={() => setTeamSize(Math.min(100, teamSize + 1))} className="w-8 h-8 rounded-lg flex items-center justify-center text-lg font-bold" style={{ background: isDark ? 'var(--color-surface-dark-3)' : 'var(--color-neutral-100)', color: txt }}>+</button>
              </div>
              <div className="text-right">
                <p className="text-lg font-bold" style={{ color: txt }}>£{monthlyTotal}</p>
                <p className="text-xs" style={{ color: txtM }}>per month</p>
              </div>
            </div>

            <button onClick={() => setStep(2)} className="w-full mt-6 py-3 bg-[var(--color-info-ios)] hover:bg-[var(--color-brand-blue-deep)] text-white font-medium rounded-lg flex items-center justify-center gap-2 transition-all" data-testid="signup-next-step2">
              Continue <ArrowRight size={16} />
            </button>
          </div>
        )}

        {/* Step 2: Details */}
        {step === 2 && (
          <div className="max-w-md mx-auto" data-testid="signup-step-details">
            <h2 className="text-2xl font-semibold text-center mb-2" style={{ color: txt }}>Your details</h2>
            <p className="text-center mb-6 text-sm" style={{ color: txtM }}>Set up your account</p>
            <div className="space-y-4">
              <div>
                <label className="block text-xs mb-1.5 uppercase tracking-wider font-medium" style={{ color: txtM }}>Full Name</label>
                <input type="text" value={fullName} onChange={e => setFullName(e.target.value)} className="w-full px-4 py-2.5 text-sm rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--color-info-ios)]" style={{ background: inputBg, border: `1px solid ${border}`, color: txt }} placeholder="John Smith" required data-testid="crm-register-name" />
              </div>
              <div>
                <label className="block text-xs mb-1.5 uppercase tracking-wider font-medium" style={{ color: txtM }}>Company Name</label>
                <input type="text" value={companyName} onChange={e => setCompanyName(e.target.value)} className="w-full px-4 py-2.5 text-sm rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--color-info-ios)]" style={{ background: inputBg, border: `1px solid ${border}`, color: txt }} placeholder="Acme Ltd" data-testid="crm-register-company" />
              </div>
              <div>
                <label className="block text-xs mb-1.5 uppercase tracking-wider font-medium" style={{ color: txtM }}>Email</label>
                <input type="email" value={email} onChange={e => setEmail(e.target.value)} className="w-full px-4 py-2.5 text-sm rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--color-info-ios)]" style={{ background: inputBg, border: `1px solid ${border}`, color: txt }} placeholder="you@company.com" required data-testid="crm-login-email" />
              </div>
              <div>
                <label className="block text-xs mb-1.5 uppercase tracking-wider font-medium" style={{ color: txtM }}>Password</label>
                <div className="relative">
                  <input type={showPwd ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)} className="w-full px-4 py-2.5 pr-10 text-sm rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--color-info-ios)]" style={{ background: inputBg, border: `1px solid ${border}`, color: txt }} placeholder="Min 6 characters" required minLength={6} data-testid="crm-login-password" />
                  <button type="button" onClick={() => setShowPwd(!showPwd)} className="absolute right-3 top-1/2 -translate-y-1/2" style={{ color: txtM }}>{showPwd ? <EyeOff size={16} /> : <Eye size={16} />}</button>
                </div>
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button onClick={() => setStep(1)} className="flex-1 py-3 rounded-lg font-medium flex items-center justify-center gap-2 transition-all" style={{ background: isDark ? 'var(--color-surface-dark-3)' : 'var(--color-neutral-100)', color: txt }}>
                <ArrowLeft size={16} /> Back
              </button>
              <button onClick={() => { if (canProceedStep2) setStep(3); else setError('Please fill in all fields'); }} className="flex-1 py-3 bg-[var(--color-info-ios)] hover:bg-[var(--color-brand-blue-deep)] text-white font-medium rounded-lg flex items-center justify-center gap-2 transition-all disabled:opacity-50" disabled={!canProceedStep2} data-testid="signup-next-step3">
                Review <ArrowRight size={16} />
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Confirmation */}
        {step === 3 && (
          <div className="max-w-md mx-auto" data-testid="signup-step-confirm">
            <h2 className="text-2xl font-semibold text-center mb-2" style={{ color: txt }}>Review & Start Trial</h2>
            <p className="text-center mb-6 text-sm" style={{ color: txtM }}>14-day free trial — no credit card required</p>

            <div className="rounded-xl overflow-hidden mb-4" style={{ background: surface, border: `1px solid ${border}` }}>
              <div className="p-4 border-b" style={{ borderColor: border }}>
                <p className="text-xs uppercase tracking-wider font-medium mb-2" style={{ color: txtM }}>Plan</p>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <CreditCard size={18} style={{ color: plan?.color || 'var(--color-info-ios)' }} />
                    <span className="font-semibold" style={{ color: txt }}>{plan?.name}</span>
                  </div>
                  <span className="font-bold" style={{ color: txt }}>£{monthlyTotal}/mo</span>
                </div>
                <p className="text-xs mt-1" style={{ color: txtM }}>£{plan?.base.toFixed(2)} base + £{plan?.perUser.toFixed(2)} x {teamSize} user{teamSize > 1 ? 's' : ''}</p>
              </div>
              <div className="p-4 border-b" style={{ borderColor: border }}>
                <p className="text-xs uppercase tracking-wider font-medium mb-2" style={{ color: txtM }}>Account</p>
                <p className="text-sm" style={{ color: txt }}>{fullName}</p>
                <p className="text-sm" style={{ color: txtM }}>{email}</p>
              </div>
              <div className="p-4">
                <p className="text-xs uppercase tracking-wider font-medium mb-2" style={{ color: txtM }}>Company</p>
                <div className="flex items-center gap-2">
                  <Building2 size={16} style={{ color: txtM }} />
                  <span className="text-sm" style={{ color: txt }}>{companyName || `${fullName}'s CRM`}</span>
                </div>
              </div>
            </div>

            <div className="p-3 rounded-lg mb-6 text-center text-sm" style={{ background: isDark ? '#1a2e1a' : '#F0FFF4', color: 'var(--color-success-alt)', border: '1px solid rgba(52,199,89,0.2)' }}>
              Your 14-day free trial starts today. You won't be charged until it ends.
            </div>

            <div className="flex gap-3">
              <button onClick={() => setStep(2)} className="flex-1 py-3 rounded-lg font-medium flex items-center justify-center gap-2" style={{ background: isDark ? 'var(--color-surface-dark-3)' : 'var(--color-neutral-100)', color: txt }}>
                <ArrowLeft size={16} /> Back
              </button>
              <button onClick={handleRegister} disabled={loading} className="flex-1 py-3 bg-[var(--color-info-ios)] hover:bg-[var(--color-brand-blue-deep)] text-white font-medium rounded-lg flex items-center justify-center gap-2 transition-all disabled:opacity-50" data-testid="signup-submit">
                {loading ? <Loader2 size={16} className="animate-spin" /> : <>Start Free Trial <ArrowRight size={16} /></>}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
