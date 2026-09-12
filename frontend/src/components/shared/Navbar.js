import React, { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/App';
import { X, Menu, Eye, EyeOff, Settings, UserCircle, LogOut, ChevronDown, Crown, Globe, Sun, Moon, Loader2, CheckCircle, HelpCircle, LifeBuoy } from 'lucide-react';
import SiteSwitcher from './SiteSwitcher';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import AccountPanel from '../../pages/AccountPanel';
import AccountSettingsModal from './AccountSettingsModal';
import AreaSwitcher from './AreaSwitcher';
import CaptchaWidget from './CaptchaWidget';
import MfaEnrolPanel from './MfaEnrolPanel';
import axios from 'axios';
import { useInlineBanner, notify } from '@/components/notifications';
import { useTranslation } from 'react-i18next';
import { setLanguagePreference } from '@/utils/languagePref';

const Navbar = ({ _onOpenSettings, onOpenMasterAdmin, onStartTour, triggerLogin }) => {
 const { user, login, logout, API, branding, theme, toggleTheme, sites, _activeSite, _setActiveSite } = useAuth();
 const { t, i18n } = useTranslation();
 const { banner: authBanner, show: showAuthBanner, clear: clearAuthBanner } = useInlineBanner();
 const [showAuth, setShowAuth] = useState(false);
 const [isLogin, setIsLogin] = useState(true);
 const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
 const [showPassword, setShowPassword] = useState(false);
 const [showAccount, setShowAccount] = useState(false);
 const [accountInitialSection, setAccountInitialSection] = useState(null);
 const [showForgotPassword, setShowForgotPassword] = useState(false);
 const [forgotEmail, setForgotEmail] = useState('');
 const [forgotSent, setForgotSent] = useState(false);
 const [forgotLoading, setForgotLoading] = useState(false);
 const [showUserMenu, setShowUserMenu] = useState(false);
 const [showLangMenu, setShowLangMenu] = useState(false);
 const [orgLogo, setOrgLogo] = useState(null);
 const [systemChoice, setSystemChoice] = useState(null); // { portal: response, crm: response }
 const [captchaToken, setCaptchaToken] = useState('');
 const [mfaChallenge, setMfaChallenge] = useState(null); // { temp_token, email }
 // Iter 216h117 — Mandatory MFA enrolment state (first-login flow for MOD HQ).
 const [mfaEnrol, setMfaEnrol] = useState(null); // { temp_token, email, reason, secret?, provisioning_uri?, qrcode_data_url? }
 const [mfaEnrolCode, setMfaEnrolCode] = useState('');
 const [mfaEnrolBackupCodes, setMfaEnrolBackupCodes] = useState(null);
 const [mfaCode, setMfaCode] = useState('');
 const [mfaBusy, setMfaBusy] = useState(false);
 const [ssoStatus, setSsoStatus] = useState({ enabled: false });

 useEffect(() => {
 axios
 .get(`${API}/auth/sso/status`)
 .then((res) => setSsoStatus(res.data || { enabled: false }))
 .catch(() => setSsoStatus({ enabled: false }));
 // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: module-level constant; identity is stable across renders.
 }, []);
 const navigate = useNavigate();
 const location = useLocation();
 // Iter 220w — return from Stripe Connect onboarding (or any deep-link that
 // wants Account Settings open). `?account=<section>` opens the settings
 // modal on that section; `?stripe=onboarded|refresh` surfaces a toast.
 useEffect(() => {
   const params = new URLSearchParams(location.search);
   const acct = params.get('account');
   const stripe = params.get('stripe');
   if (!acct && !stripe) return;
   if (acct || stripe) {
     setAccountInitialSection(acct || 'billing');
     setShowAccount(true);
   }
   if (stripe === 'onboarded') {
     notify.success('Stripe connected', 'Finish any remaining steps in Stripe to start taking payments.');
   } else if (stripe === 'refresh') {
     notify.info('Stripe onboarding paused', 'Pick up where you left off any time from the setup checklist.');
   }
   // Strip the params so a refresh doesn't re-trigger.
   params.delete('account');
   params.delete('stripe');
   const qs = params.toString();
   navigate({ pathname: location.pathname, search: qs ? `?${qs}` : '' }, { replace: true });
 // eslint-disable-next-line react-hooks/exhaustive-deps
 }, [location.search]);
 const isOnDashboard = location.pathname.startsWith('/dashboard');
 const isOnPulse = location.pathname.startsWith('/pulse');
 // Iter 215bi — Settings should be reachable from any authenticated surface
 // (operations, memberships, CRM, marketing, master-admin), not just /dashboard.
 const _isOnAuthApp = isOnDashboard || isOnPulse
   || location.pathname.startsWith('/master-admin')
   || location.pathname.startsWith('/memberships')
   || location.pathname.startsWith('/marketing')
   || location.pathname.startsWith('/crm')
   || location.pathname.startsWith('/operations');
 // Pulse-branded users should see the Pulse Fitness logo across all their modules
 // (Operations, Memberships, Gym Floor) so the header stays visually stable when
 // switching between them.
 //
 // Iter 216h118 — MOD users (mod_site / mod_branch / mod_org) are
 // Pulse Fitness customers per the iter 216h113 routing rule. They
 // MUST see the Pulse Fitness logo, never the Pulse Fitness lockup.
 const pulseAccount = (
   user?.account_type === 'pulse_pro' || user?.account_type === 'lite' ||
   user?.account_type === 'mod_site' || user?.account_type === 'mod_branch' ||
   user?.account_type === 'mod_org'
 );
 const showPulseBrand = isOnPulse || pulseAccount;
 const _isAdmin = user?.is_master_admin || user?.account_type === 'full';
 const brandColor = branding?.primary_color || 'var(--color-brand-blue)';

 // Listen for open-signup event from homepage CTAs
 React.useEffect(() => {
 const handleOpenSignup = () => {
 setIsLogin(false);
 setShowAuth(true);
 };
 const handleOpenLogin = () => {
 setIsLogin(true);
 setShowAuth(true);
 };
 window.addEventListener('open-signup', handleOpenSignup);
 window.addEventListener('open-login', handleOpenLogin);
 return () => {
 window.removeEventListener('open-signup', handleOpenSignup);
 window.removeEventListener('open-login', handleOpenLogin);
 };
 }, []);

 // Auto-open login dialog when triggerLogin prop is set (from /login route)
 React.useEffect(() => {
 if (triggerLogin && !user) {
 // Delay to ensure Dialog portal is mounted after initial render
 const frame = requestAnimationFrame(() => {
 setTimeout(() => {
 setIsLogin(true);
 setShowAuth(true);
 }, 100);
 });
 return () => cancelAnimationFrame(frame);
 }
 }, [triggerLogin, user]);

 React.useEffect(() => {
 if (user && API) {
 const token = localStorage.getItem('token');
 axios.get(`${API}/organization/logo`, { headers: { Authorization: `Bearer ${token}` } })
 .then(res => {
 const url = res.data.logo_url;
 if (url) {
 // If relative path starting with /api, prepend the backend URL base
 const baseUrl = API.replace('/api', '');
 setOrgLogo(url.startsWith('/') ? `${baseUrl}${url}` : url);
 }
 })
 .catch(() => {});
 }
 }, [user, API]);
 
 const [formData, setFormData] = useState({
 email: '',
 password: '',
 full_name: '',
 company_name: '',
 company_code: ''
 });

 const handleForgotPassword = async (e) => {
 e.preventDefault();
 setForgotLoading(true);
 try {
 await axios.post(
 `${API}/auth/forgot-password`,
 { email: forgotEmail },
 { headers: captchaToken ? { 'X-Captcha-Token': captchaToken } : {} },
 );
 setForgotSent(true);
 clearAuthBanner();
 } catch {
 showAuthBanner({ tone: 'error', title: 'Reset link could not be sent', detail: 'Please check the email address and try again.' });
 }
 setForgotLoading(false);
 };

 const loginToPortal = (response) => {
 login(response.data.token, response.data.user);
 setShowAuth(false);
 setSystemChoice(null);
 notify.success(t('auth.login_success'));
 const u = response.data.user;
 // Iter 222 — Pulse Master Admins land on their MODULES (Pulse portal)
 // at login, not the Master Admin console. They reach the console on
 // demand via the Dashboard → Master Admin button. Full Pulse Fitness platform
 // admins still go straight to /master-admin.
 if (u?.is_master_admin) {
 navigate('/master-admin');
 } else if (u?.is_pulse_admin || u?.account_type === 'lite' || u?.account_type === 'pulse_pro') {
 navigate('/pulse');
 } else {
 navigate('/dashboard');
 }
 };

 const loginToCRM = (crmRes) => {
 if (crmRes.data.requires_2fa) {
 localStorage.setItem('crm_token', crmRes.data.temp_token);
 } else {
 localStorage.setItem('crm_token', crmRes.data.token);
 }
 sessionStorage.setItem('crm_active_session', '1');
 setShowAuth(false);
 setSystemChoice(null);
 notify.success(t('auth.login_success'));
 window.dispatchEvent(new Event('pwa-check-install'));
 navigate('/crm');
 };

 const handleMfaVerify = async (e) => {
 e.preventDefault();
 if (!mfaChallenge) return;
 setMfaBusy(true);
 try {
 const res = await axios.post(`${API}/auth/mfa/verify`, {
 temp_token: mfaChallenge.temp_token,
 code: mfaCode,
 });
 loginToPortal({ data: res.data });
 setMfaChallenge(null);
 setMfaCode('');
 } catch (err) {
 showAuthBanner({ tone: 'error', title: 'Verification failed', detail: err.response?.data?.detail || 'Invalid code. Please try again.' });
 }
 setMfaBusy(false);
 };

 const handleAuth = async (e) => {
 e.preventDefault();
 clearAuthBanner();
 if (!isLogin) {
 try {
 const response = await axios.post(`${API}/auth/register`, formData);
 login(response.data.token, response.data.user);
 setShowAuth(false);
 notify.success(t('auth.signup_success'));
 navigate(response.data.user?.account_type === 'lite' ? '/pulse' : '/dashboard');
 } catch (error) {
 showAuthBanner({ tone: 'error', title: 'Sign-up failed', detail: error.response?.data?.detail || t('auth.login_failed') });
 }
 return;
 }

 // Try both auth endpoints in parallel
 const captchaHeader = captchaToken ? { 'X-Captcha-Token': captchaToken } : {};
 const [portalResult, crmResult] = await Promise.allSettled([
 axios.post(`${API}/auth/login`, formData, { headers: captchaHeader }),
 axios.post(`${API}/crm/auth/login`, { email: formData.email, password: formData.password }, { headers: captchaHeader }),
 ]);

 const portalOk = portalResult.status === 'fulfilled';
 const crmOk = crmResult.status === 'fulfilled';

 // MFA challenge path — portal returned requires_mfa
 if (portalOk && portalResult.value.data?.requires_mfa) {
 setMfaChallenge({
 temp_token: portalResult.value.data.temp_token,
 email: portalResult.value.data.user?.email || formData.email,
 });
 return;
 }
 // Iter 216h117 — Mandatory MFA enrolment (first login for MOD HQ).
 if (portalOk && portalResult.value.data?.requires_mfa_enrolment) {
 setMfaEnrol({
 temp_token: portalResult.value.data.temp_token,
 email: portalResult.value.data.user?.email || formData.email,
 reason: portalResult.value.data.reason,
 });
 return;
 }

    if (portalOk && crmOk) {
 // Master admin — skip chooser, go straight to admin dashboard
 if (portalResult.value.data.user?.is_master_admin || portalResult.value.data.user?.is_pulse_admin) {
 loginToPortal(portalResult.value);
 return;
 }
 // User exists in BOTH systems — show chooser
 setSystemChoice({ portal: portalResult.value, crm: crmResult.value });
 } else if (portalOk) {
 loginToPortal(portalResult.value);
 } else if (crmOk) {
 loginToCRM(crmResult.value);
 } else {
 // Last-ditch: shared Gym Floor credentials. Saves us from having a
 // separate kiosk login page — everyone uses this same modal.
 const looksLikeUsername = formData.email && !formData.email.includes('@');
 if (looksLikeUsername) {
 try {
 const gf = await axios.post(`${API}/gym-floor/login`, { username: formData.email, password: formData.password });
 const session = { ...gf.data, logged_in_at: new Date().toISOString() };
 localStorage.setItem('gym_floor_session', JSON.stringify(session));
 setShowAuth(false);
 navigate('/gym-floor', { replace: true });
 return;
 } catch (_) {
 // fall through to the original error toast
 }
 }
 showAuthBanner({ tone: 'error', title: 'Login failed', detail: portalResult.reason?.response?.data?.detail || t('auth.login_failed') });
 }
 };

 const publicLinks = [
 { to: '/', label: t('nav.home'), testId: 'nav-home' },
 { to: '/features', label: t('nav.features'), testId: 'nav-features' },
 { to: '/pricing', label: t('nav.pricing'), testId: 'nav-pricing' },
 { to: '/about', label: t('nav.about'), testId: 'nav-about' },
 { to: '/contact', label: t('nav.contact'), testId: 'nav-contact' },
 ];

 // Iter 215az — for Pulse Fitness surfaces (non-Pulse, default branding) we
 // now render the actual Pulse Fitness lockup (mark + "Pulse Fitness" wordmark) in
 // the navbar, matching the marketing site. Custom orgs that uploaded
 // their own logo (orgLogo) still get their own branding; Pulse
 // accounts continue to see PulseFitnessLogo. The fallback initial-box
 // (`brandColor` square) is reserved for orgs without a logo who don't
 // map to either brand.
 const _isPulseFitnessBrand = !showPulseBrand && !orgLogo && (!user || (
   !pulseAccount && (branding?.company_name || '').toLowerCase().includes('gymaxis') !== false
 ));
 // Default: show Pulse Fitness lockup whenever Pulse isn't active and the org
 // hasn't uploaded a custom logo. This covers logged-out, master admin,
 // and full-account Pulse Fitness customers.
 const shouldShowPulseFitnessLockup = !showPulseBrand && !orgLogo;

 return (
 <>
 <nav
className="fixed top-0 left-0 right-0 z-50 border-b border-white/10"
style={{
backgroundColor: '#000000',
fontFamily: "'Proxima Nova', 'Inter', system-ui, sans-serif",
// Force a permanent dark header regardless of the app's light/dark theme
// (Pulse Fitness marketing: header must always be black with white text).
'--theme-text': '#ffffff',
'--theme-text-muted': 'rgba(255,255,255,0.82)',
'--theme-border': 'rgba(255,255,255,0.18)',
'--theme-surface': '#0a0a0a',
}}
>
 <div className="max-w-7xl mx-auto px-4">
 <div className="flex justify-between items-center h-20">
 <Link to={user ? (showPulseBrand ? '/pulse' : '/dashboard') : '/'} className="flex items-center space-x-2.5" data-testid="nav-logo">
 {/* Iter 216h59 — uploaded org logo now wins over Pulse / Pulse Fitness
     defaults. Per operator request: "Once the user uploads a logo
     it should overtake the Pulse Fitness/Pulse Fitness logo in the
     navbar." Falls back to Pulse → Pulse Fitness → initial-box in that
     order when no custom logo is uploaded. */}
 {orgLogo ? (
 <img src={orgLogo} alt={branding?.company_name || 'Logo'} className="h-10 w-10 object-contain rounded" data-testid="org-logo" />
 ) : showPulseBrand ? (
 <img src="https://customer-assets.emergentagent.com/job_maintenance-hub-357/artifacts/iscy9t7o_Pulse%20Fitness%20Primary%20Logo%20Badge%20RGB.jpg" alt="Pulse Fitness" className="h-10 rounded-md object-cover" style={{ objectPosition: 'center', aspectRatio: '3.8/1', clipPath: 'inset(12% 3% 12% 3% round 6px)' }} data-testid="pulse-logo" />
 ) : shouldShowPulseFitnessLockup ? (
 <img src="https://customer-assets.emergentagent.com/job_maintenance-hub-357/artifacts/iscy9t7o_Pulse%20Fitness%20Primary%20Logo%20Badge%20RGB.jpg" alt="Pulse Fitness" className="h-10 rounded-md object-cover" style={{ objectPosition: 'center', aspectRatio: '3.8/1', clipPath: 'inset(12% 3% 12% 3% round 6px)' }} data-testid="pulse-logo" />
 ) : (
 <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ backgroundColor: brandColor }}>
 <span className="text-white font-bold text-xl">{branding?.company_name?.charAt(0) || 'P'}</span>
 </div>
 )}
 <div>
 {orgLogo ? (
 <span className="font-bold text-xl tracking-tight" style={{ color: 'var(--theme-text)' }} data-testid="org-name-label">
 {branding?.company_name || ''}
 </span>
 ) : showPulseBrand ? null : shouldShowPulseFitnessLockup ? (
 (user && branding?.company_name && !branding.company_name.toLowerCase().includes('gymaxis')) ? (
 <span className="font-bold text-xl tracking-tight" style={{ fontFamily: "'Satoshi', 'Inter', system-ui, sans-serif", color: 'var(--theme-text)' }}>
 {branding.company_name}
 </span>
 ) : null
 ) : (
 <span className="font-bold text-xl" style={{ color: 'var(--theme-text)' }}>{(user && branding?.company_name) || ((user?.account_type === 'pulse_pro' || user?.account_type === 'lite') ? 'Pulse Fitness' : 'Pulse Fitness AI')}</span>
 )}
 </div>
 </Link>
 
 {/* Show public nav links only when NOT logged in */}
 {!user && (
 <div className="hidden md:flex items-center space-x-8">
 {publicLinks.map(link => (
 <Link key={link.to} to={link.to} className="hover:opacity-80 transition-all duration-300" style={{ color: 'var(--theme-text-muted)' }} data-testid={link.testId}>{link.label}</Link>
 ))}
 </div>
 )}
 
 <div className="hidden md:flex items-center space-x-3">
 {/* Theme Toggle */}
 <button
 onClick={toggleTheme}
 className="theme-toggle-btn"
 data-testid="theme-toggle-btn"
 aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
 >
 {theme === 'dark' ? <Sun size={16} className="text-amber-400" /> : <Moon size={16} className="text-slate-300" />}
 </button>

 {/* Language Switcher */}
 <div className="relative">
 <button
 onClick={() => setShowLangMenu(!showLangMenu)}
 className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border hover:opacity-80 transition-colors"
 style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}
 data-testid="lang-switcher-btn"
 >
 <Globe size={15} />
 <span className="text-xs font-medium uppercase">{i18n.language?.substring(0, 2)}</span>
 </button>
 {showLangMenu && (
 <>
 <div className="fixed inset-0 z-40" onClick={() => setShowLangMenu(false)} />
 <div className="absolute right-0 top-full mt-2 w-40 rounded-lg shadow-xl z-50 overflow-hidden" style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }} data-testid="lang-dropdown">
 {[
 { code: 'en', label: 'English', flag: '\ud83c\uddec\ud83c\udde7' },
 { code: 'fr', label: 'Fran\u00e7ais', flag: '\ud83c\uddeb\ud83c\uddf7' },
 { code: 'de', label: 'Deutsch', flag: '\ud83c\udde9\ud83c\uddea' }
 ].map(lang => (
 <button
 key={lang.code}
 onClick={() => {
   setShowLangMenu(false);
   // Iter 239 — persist per-user so the language follows them across
   // devices. Offline-safe: switches + persists locally now, queues the
   // account sync for retry if there's no signal (field engineers).
   setLanguagePreference(lang.code);
 }}
 className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
 i18n.language?.startsWith(lang.code)
 ? 'font-medium'
 : 'opacity-70 hover:opacity-100'
 }`}
 style={{ color: 'var(--theme-text)' }}
 data-testid={`lang-option-${lang.code}`}
 >
 <span className="text-base">{lang.flag}</span>
 {lang.label}
 </button>
 ))}
 </div>
 </>
 )}
 </div>

 {user ? (
 <>
 {!isOnDashboard && !isOnPulse && !showPulseBrand && (
 <Link to="/dashboard" data-testid="nav-dashboard-link">
 <Button className="text-white" style={{ backgroundColor: brandColor }} data-testid="nav-dashboard-btn">{t('nav.dashboard')}</Button>
 </Link>
 )}

 {/* Site Switcher — owners only, when >1 site.
     Iter 216h31 — replaced bespoke inline dropdown with the canonical
     <SiteSwitcher> so the Pulse Fitness Pro `/dashboard` shows the same
     HQ-star-first list that Pulse Pro / Lite operators see on /pulse.
     Backend (/api/sites) auto-creates a real Head Office row and
     sorts it to the top, so the operator can always pick HQ even
     when no site was originally flagged as head office.
     Iter 216bk — hidden on /pulse because the operations dashboard
     renders its own viewport-safe SiteSwitcher in the welcome banner. */}
 {sites.length > 1 && isOnDashboard && !isOnPulse && user?.role === 'owner' && !user?.is_master_admin && (
 <SiteSwitcher />
 )}
 
 {/* Iter 283 — Switch area (Service Desk / Engineer app), next to account menu */}
 <AreaSwitcher user={user} tone="header" />

 {/* User Menu Dropdown */}
 <div className="relative">
 <button
 onClick={() => setShowUserMenu(!showUserMenu)}
 className="flex items-center gap-2 px-3 py-2 rounded-lg border hover:opacity-80 transition-colors"
 style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
 data-testid="nav-user-menu-btn"
 >
 <div className="w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-bold" style={{ backgroundColor: brandColor }}>
 {user?.full_name?.charAt(0)?.toUpperCase() || 'U'}
 </div>
 <span className="text-sm max-w-[120px] truncate" style={{ color: 'var(--theme-text)' }}>{user?.full_name || 'User'}</span>
 <ChevronDown size={14} className={`transition-transform ${showUserMenu ? 'rotate-180' : ''}`} style={{ color: 'var(--theme-text-muted)' }} />
 </button>

 {showUserMenu && (
 <>
 <div className="fixed inset-0 z-40" onClick={() => setShowUserMenu(false)} />
 <div className="absolute right-0 top-full mt-2 w-56 rounded-lg shadow-xl z-50 overflow-hidden" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', border: '1px solid var(--theme-border)' }} data-testid="user-dropdown-menu">
 <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--theme-border)' }}>
 <p className="text-sm font-medium truncate" style={{ color: 'var(--theme-text)' }}>{user?.full_name}</p>
 <p className="text-xs truncate" style={{ color: 'var(--theme-text-muted)' }}>{user?.email}</p>
 </div>
 <div className="py-1">
 <button
 onClick={() => { setShowAccount(true); setShowUserMenu(false); }}
 className="w-full flex items-center gap-3 px-4 py-2.5 text-sm hover:opacity-80 transition-colors"
 style={{ color: 'var(--theme-text-muted)' }}
 data-testid="nav-account-btn"
 >
 <UserCircle size={16} /> {t('nav.account')}
 </button>
 <button
 onClick={() => { 
 setShowUserMenu(false);
 // Pass current module hint so Help filters relevantly.
 const moduleHint = location.pathname.startsWith('/crm')
   ? 'crm'
   : location.pathname.startsWith('/memberships')
     ? 'memberships'
     : location.pathname.startsWith('/marketing')
       ? 'marketing'
       : 'operations';
 navigate(`/help?module=${moduleHint}`);
 }}
 className="w-full flex items-center gap-3 px-4 py-2.5 text-sm hover:opacity-80 transition-colors"
 style={{ color: 'var(--theme-text-muted)' }}
 data-testid="nav-help-btn"
 >
 <LifeBuoy size={16} /> {t('nav.help_tutorials', 'Help & Tutorials')}
 </button>
 {/* Settings option removed iter202 — settings now live inside Account modal (Preferences section) */}
 {(isOnDashboard || isOnPulse) && onStartTour && (
 <button
 onClick={() => { onStartTour(); setShowUserMenu(false); }}
 className="w-full flex items-center gap-3 px-4 py-2.5 text-sm hover:opacity-80 transition-colors"
 style={{ color: 'var(--theme-text-muted)' }}
 data-testid="nav-start-tour-btn"
 >
 <HelpCircle size={16} /> {t('nav.take_tour', 'Take a Tour')}
 </button>
 )}
 {(user?.is_master_admin || user?.is_pulse_admin) && (isOnDashboard || isOnPulse) && (
 <button
 onClick={() => {
 if (onOpenMasterAdmin) onOpenMasterAdmin();
 setShowUserMenu(false);
 }}
 className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-orange-400 hover:text-orange-300 hover:bg-white/5 transition-colors"
 data-testid="nav-master-admin-btn"
 >
 <Crown size={16} /> {t('nav.master_admin')}
 </button>
 )}
 </div>
 <div className="py-1" style={{ borderTop: '1px solid var(--theme-border)' }}>
 <button
 onClick={() => { logout(); setShowUserMenu(false); }}
 className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-red-400 hover:text-red-300 hover:bg-white/5 transition-colors"
 data-testid="nav-logout-btn"
 >
 <LogOut size={16} /> {t('nav.logout')}
 </button>
 </div>
 </div>
 </>
 )}
 </div>
 </>
 ) : (
 <>
 <Button onClick={() => { setIsLogin(true); setShowAuth(true); }} variant="outline" className="hover:opacity-80" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="nav-login-btn">{t('nav.login')}</Button>
 <Button onClick={() => { setIsLogin(false); setShowAuth(true); }} className="" data-testid="nav-trial-btn">{t('nav.start_free_trial')}</Button>
 </>
 )}
 </div>
 
 <div className="md:hidden flex items-center gap-2">
 <button
 onClick={toggleTheme}
 className="theme-toggle-btn"
 data-testid="mobile-theme-toggle"
 aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
 >
 {theme === 'dark' ? <Sun size={16} className="text-amber-400" /> : <Moon size={16} className="text-slate-300" />}
 </button>
 <button className="text-white p-2" onClick={() => setMobileMenuOpen(!mobileMenuOpen)} data-testid="mobile-menu-toggle" style={{ color: 'var(--theme-text)' }}>
 {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
 </button>
 </div>
 </div>
 </div>
 
 {mobileMenuOpen && (
 <div className="md:hidden" style={{ background: 'var(--theme-surface)', borderTop: '1px solid var(--theme-border)' }} data-testid="mobile-menu">
 <div className="px-4 py-4 space-y-3">
 {!user && publicLinks.map(link => (
 <Link key={link.to} to={link.to} className="block hover:opacity-80" style={{ color: 'var(--theme-text-muted)' }} data-testid={`mobile-${link.testId}`}>{link.label}</Link>
 ))}
 {user ? (
 <>
 {/* Iter 284 — Switch Area now in the mobile hamburger menu (header is
     too condensed on mobile). Renders only when 2+ areas are reachable. */}
 <div className="pb-1">
 <AreaSwitcher user={user} tone="header" className="w-full" />
 </div>
 {/* Dashboard button hidden for Pulse users on mobile (parity with desktop) —
     they rely on Switch Area + the pill tabs instead. */}
 {!isOnDashboard && !isOnPulse && !showPulseBrand && (
 <Link to="/dashboard" className="block" data-testid="mobile-dashboard-link">
 <Button className="w-full" data-testid="mobile-dashboard-btn">{t('nav.dashboard')}</Button>
 </Link>
 )}
 <button
 onClick={() => { setShowAccount(true); setMobileMenuOpen(false); }}
 className="w-full flex items-center gap-2 px-3 py-2 hover:opacity-80"
 style={{ color: 'var(--theme-text-muted)' }}
 data-testid="mobile-account-btn"
 >
 <UserCircle size={16} /> {t('nav.account')}
 </button>
 {/* Iter 216h235 — Help & Tutorials parity with desktop user menu.
     Was previously desktop-only; Lee's mobile QA pass surfaced it
     missing. Picks the same module hint from location.pathname as
     the desktop button does (line 454-461). */}
 <button
 onClick={() => {
   setMobileMenuOpen(false);
   const moduleHint = location.pathname.startsWith('/crm')
     ? 'crm'
     : location.pathname.startsWith('/memberships')
       ? 'memberships'
       : location.pathname.startsWith('/marketing')
         ? 'marketing'
         : 'operations';
   navigate(`/help?module=${moduleHint}`);
 }}
 className="w-full flex items-center gap-2 px-3 py-2 hover:opacity-80"
 style={{ color: 'var(--theme-text-muted)' }}
 data-testid="mobile-help-btn"
 >
 <LifeBuoy size={16} /> {t('nav.help_tutorials', 'Help & Tutorials')}
 </button>
 {/* Mobile: settings option removed iter202 — moved into Account modal */}
 {(user?.is_master_admin || user?.is_pulse_admin) && (isOnDashboard || isOnPulse) && onOpenMasterAdmin && (
 <button
 onClick={() => { onOpenMasterAdmin(); setMobileMenuOpen(false); }}
 className="w-full flex items-center gap-2 px-3 py-2 text-orange-400 hover:text-orange-300"
 data-testid="mobile-master-admin-btn"
 >
 <Crown size={16} /> {t('nav.master_admin')}
 </button>
 )}
 {(isOnDashboard || isOnPulse) && onStartTour && (
 <button
 onClick={() => { onStartTour(); setMobileMenuOpen(false); }}
 className="w-full flex items-center gap-2 px-3 py-2 hover:opacity-80"
 style={{ color: 'var(--theme-text-muted)' }}
 data-testid="mobile-start-tour-btn"
 >
 <HelpCircle size={16} /> {t('nav.take_tour', 'Take a Tour')}
 </button>
 )}
 <Button onClick={logout} variant="outline" className="w-full" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="mobile-logout-btn">{t('nav.logout')}</Button>
 </>
 ) : (
 <>
 <Button onClick={() => { setIsLogin(true); setShowAuth(true); setMobileMenuOpen(false); }} variant="outline" className="w-full" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="mobile-login-btn">{t('nav.login')}</Button>
 <Button
  onClick={() => { setIsLogin(false); setShowAuth(true); setMobileMenuOpen(false); }}
  className="w-full justify-center hover:opacity-90 border-0 font-semibold"
  style={{
    background: 'linear-gradient(135deg, var(--gx-brand-from, #2563EB) 0%, var(--gx-brand-to, #9D4CDD) 100%)',
    color: '#fff',
  }}
  data-testid="mobile-trial-btn"
>{t('nav.start_free_trial')}</Button>
 </>
 )}
 </div>
 </div>
 )}
 </nav>
 
 {/* Auth Dialog */}
 <Dialog open={showAuth} onOpenChange={(open) => { setShowAuth(open); if (!open) { setShowForgotPassword(false); setForgotSent(false); setForgotEmail(''); setSystemChoice(null); setMfaChallenge(null); setMfaCode(''); clearAuthBanner(); } }}>
 <DialogContent className="bg-[var(--theme-surface)] border-white/10 text-white" data-testid="auth-dialog">
 <DialogHeader>
 <DialogTitle className="text-2xl font-bold mb-4" data-testid="auth-dialog-title">
 {mfaChallenge ? 'Two-factor verification' : systemChoice ? 'Choose Your Workspace' : showForgotPassword ? 'Reset Password' : isLogin ? t('nav.login') : t('auth.signup_title')}
 </DialogTitle>
 </DialogHeader>

 {authBanner && <div className="mb-3">{authBanner}</div>}

 {mfaEnrol ? (
 <MfaEnrolPanel
 enrol={mfaEnrol}
 setEnrol={setMfaEnrol}
 code={mfaEnrolCode}
 setCode={setMfaEnrolCode}
 backupCodes={mfaEnrolBackupCodes}
 setBackupCodes={setMfaEnrolBackupCodes}
 onComplete={(loginRes) => {
 setMfaEnrol(null);
 setMfaEnrolCode('');
 loginToPortal({ data: loginRes });
 }}
 />
 ) : mfaChallenge ? (
 <form onSubmit={handleMfaVerify} className="space-y-4" data-testid="mfa-challenge-form">
 <p className="text-sm text-[var(--color-text-muted)]">
 Enter the 6-digit code from your authenticator app for <span className="text-white">{mfaChallenge.email}</span>.
 You can also use a backup code.
 </p>
 <Input
 autoFocus
 placeholder="123456"
 value={mfaCode}
 onChange={(e) => setMfaCode(e.target.value.trim())}
 maxLength={8}
 className="bg-[var(--color-ink-alt)] border-white/10 text-white tracking-widest text-lg text-center"
 data-testid="mfa-challenge-input"
 />
 <Button
 type="submit"
 className="w-full"
 disabled={mfaBusy || !mfaCode}
 data-testid="mfa-challenge-submit"
 >
 {mfaBusy ? <Loader2 size={16} className="animate-spin mr-2" /> : null}
 Verify
 </Button>
 <button
 type="button"
 onClick={() => { setMfaChallenge(null); setMfaCode(''); }}
 className="w-full text-center text-sm text-[var(--color-text-muted)] hover:text-white"
 data-testid="mfa-challenge-cancel"
 >
 Cancel
 </button>
 </form>
 ) : systemChoice ? (
 <div className="space-y-3" data-testid="system-chooser">
 <p className="text-[var(--color-text-muted)] text-sm">Your account has access to multiple systems. Where would you like to go?</p>
 <button
 onClick={() => loginToPortal(systemChoice.portal)}
 className="w-full flex items-center gap-4 p-4 rounded-xl border border-white/10 hover:border-[rgb(var(--rgb-brand-blue)/0.5)] hover:bg-[rgb(var(--rgb-brand-blue)/0.05)] transition-all text-left group"
 data-testid="choose-service-portal"
 >
 <div className="w-12 h-12 rounded-xl bg-[rgb(var(--rgb-brand-blue)/0.1)] flex items-center justify-center shrink-0 group-hover:bg-[rgb(var(--rgb-brand-blue)/0.2)] transition-colors">
 <Settings size={22} className="text-[var(--color-brand-blue)]" />
 </div>
 <div>
 <p className="text-white font-semibold text-base">Operations Portal</p>
 <p className="text-[var(--color-text-muted)] text-xs mt-0.5">Equipment management, maintenance & compliance</p>
 </div>
 <ChevronDown size={16} className="text-[var(--color-text-muted)] -rotate-90 ml-auto shrink-0 group-hover:text-[var(--color-brand-blue)] transition-colors" />
 </button>
 <button
 onClick={() => loginToCRM(systemChoice.crm)}
 className="w-full flex items-center gap-4 p-4 rounded-xl border border-white/10 hover:border-emerald-500/50 hover:bg-emerald-500/5 transition-all text-left group"
 data-testid="choose-crm"
 >
 <div className="w-12 h-12 rounded-xl bg-emerald-500/10 flex items-center justify-center shrink-0 group-hover:bg-emerald-500/20 transition-colors">
 <UserCircle size={22} className="text-emerald-500" />
 </div>
 <div>
 <p className="text-white font-semibold text-base">CRM System</p>
 <p className="text-[var(--color-text-muted)] text-xs mt-0.5">Sales pipeline, contacts, contracts & quotes</p>
 </div>
 <ChevronDown size={16} className="text-[var(--color-text-muted)] -rotate-90 ml-auto shrink-0 group-hover:text-emerald-500 transition-colors" />
 </button>
 <button onClick={() => setSystemChoice(null)} className="w-full text-center text-sm text-[var(--color-text-muted)] hover:text-white mt-2" data-testid="choose-back-btn">
 Back to login
 </button>
 </div>
 ) : showForgotPassword ? (
 forgotSent ? (
 <div className="text-center py-4">
 <CheckCircle size={40} className="text-emerald-500 mx-auto mb-3" />
 <p className="text-white font-medium mb-2">Check Your Email</p>
 <p className="text-[var(--color-text-muted)] text-sm mb-4">If an account exists with <strong>{forgotEmail}</strong>, we've sent a password reset link.</p>
 <Button onClick={() => { setShowForgotPassword(false); setForgotSent(false); }} className="w-full" variant="outline" data-testid="forgot-back-btn">
 Back to Login
 </Button>
 </div>
 ) : (
 <form onSubmit={handleForgotPassword} className="space-y-4">
 <p className="text-[var(--color-text-muted)] text-sm">Enter your email address and we'll send you a link to reset your password.</p>
 <div>
 <Label htmlFor="forgot-email" className="text-white">Email Address</Label>
 <Input
 id="forgot-email"
 type="email"
 value={forgotEmail}
 onChange={e => setForgotEmail(e.target.value)}
 required
 placeholder="you@example.com"
 className="bg-[var(--color-ink-alt)] border-white/10 text-white"
 data-testid="forgot-email-input"
 />
 </div>
 <CaptchaWidget action="forgot_password" onToken={setCaptchaToken} />
 <Button type="submit" className="w-full" disabled={forgotLoading} data-testid="forgot-submit-btn">
 {forgotLoading ? <Loader2 size={16} className="animate-spin mr-2" /> : null}
 Send Reset Link
 </Button>
 <button type="button" onClick={() => setShowForgotPassword(false)} className="w-full text-center text-sm text-[var(--color-text-muted)] hover:text-white" data-testid="forgot-cancel-btn">
 Back to Login
 </button>
 </form>
 )
 ) : (
 <>
 <form onSubmit={handleAuth} className="space-y-4">
 <div>
 <Label htmlFor="email" className="text-white">{t('auth.email')}</Label>
 <Input
 id="email"
 type="text"
 inputMode="email"
 autoComplete="username"
 value={formData.email}
 onChange={(e) => setFormData({...formData, email: e.target.value})}
 required
 placeholder="you@gym.com or your kiosk username"
 className="bg-[var(--color-ink-alt)] border-white/10 text-white"
 data-testid="auth-email-input"
 />
 </div>
 <div>
 <Label htmlFor="password" className="text-white">{t('auth.password')}</Label>
 <div className="relative">
 <Input
 id="password"
 type={showPassword ? 'text' : 'password'}
 value={formData.password}
 onChange={(e) => setFormData({...formData, password: e.target.value})}
 required
 className="bg-[var(--color-ink-alt)] border-white/10 text-white pr-10"
 data-testid="auth-password-input"
 />
 <button
 type="button"
 onClick={() => setShowPassword(!showPassword)}
 className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] hover:text-white transition-colors"
 data-testid="password-toggle-btn"
 >
 {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
 </button>
 </div>
 </div>
 {isLogin && (
 <button type="button" onClick={() => setShowForgotPassword(true)} className="text-xs text-[var(--color-text-muted)] hover:text-white transition-colors" data-testid="forgot-password-link">
 Forgot your password?
 </button>
 )}
 {!isLogin && (
 <>
 <div>
 <Label htmlFor="full_name" className="text-white">{t('auth.full_name')}</Label>
 <Input
 id="full_name"
 value={formData.full_name}
 onChange={(e) => setFormData({...formData, full_name: e.target.value})}
 required={!isLogin}
 className="bg-[var(--color-ink-alt)] border-white/10 text-white"
 data-testid="auth-fullname-input"
 />
 </div>
 <div>
 <Label htmlFor="company_code" className="text-white">Company Code (Join existing gym)</Label>
 <Input
 id="company_code"
 value={formData.company_code}
 onChange={(e) => setFormData({...formData, company_code: e.target.value.toUpperCase()})}
 placeholder="Leave blank to create new organization"
 className="bg-[var(--color-ink-alt)] border-white/10 text-white font-mono"
 data-testid="auth-company-code-input"
 />
 <p className="text-xs text-[var(--color-text-muted)] mt-1">Enter code to join an existing gym, or leave blank to create your own</p>
 </div>
 {!formData.company_code && (
 <div>
 <Label htmlFor="company_name" className="text-white">Your Gym Name</Label>
 <Input
 id="company_name"
 value={formData.company_name}
 onChange={(e) => setFormData({...formData, company_name: e.target.value})}
 placeholder="Main Street Fitness"
 className="bg-[var(--color-ink-alt)] border-white/10 text-white"
 data-testid="auth-company-input"
 />
 </div>
 )}
 </>
 )}
 <CaptchaWidget action={isLogin ? 'login' : 'register'} onToken={setCaptchaToken} />
 <Button type="submit" className="w-full" data-testid="auth-submit-btn">
 {isLogin ? t('auth.login_btn') : t('auth.signup_btn')}
 </Button>
 {isLogin && ssoStatus.enabled && (
 <>
 <div className="flex items-center gap-3 my-1">
 <div className="flex-1 h-px bg-white/10" />
 <span className="text-xs text-white/40">or</span>
 <div className="flex-1 h-px bg-white/10" />
 </div>
 <Button
 type="button"
 onClick={() => { window.location.href = `${API}/auth/sso/start`; }}
 variant="outline"
 className="w-full border-white/20 text-white hover:bg-white/5"
 data-testid="sso-login-btn"
 >
 Sign in with SSO
 </Button>
 </>
 )}
 </form>
 <p className="text-center text-sm text-[var(--color-text-muted)] mt-4">
 {isLogin ? t('auth.no_account') : t('auth.have_account')}{' '}
 <button 
 onClick={() => setIsLogin(!isLogin)} 
 className="text-[var(--color-brand-blue)] hover:text-[var(--color-brand-blue-alt)]"
 data-testid="auth-toggle-btn"
 >
 {isLogin ? t('nav.signup') : t('nav.login')}
 </button>
 </p>
 </>
 )}
 </DialogContent>
 </Dialog>

 {/* Account Panel */}
 {/* Account settings — Owners/Managers/Staff get the redesigned modal;
     Master admins keep the legacy panel (they have a dedicated console). */}
 {user?.is_master_admin || user?.is_pulse_admin ? (
   <AccountPanel open={showAccount} onClose={() => { setShowAccount(false); setAccountInitialSection(null); }} />
 ) : (
   <AccountSettingsModal open={showAccount} onClose={() => { setShowAccount(false); setAccountInitialSection(null); }} initialSection={accountInitialSection} />
 )}
 </>
 );
};

export default Navbar;
