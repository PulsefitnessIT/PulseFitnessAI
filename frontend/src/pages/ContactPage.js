import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Navbar from '../components/shared/Navbar';
import Footer from '../components/shared/Footer';
import CaptchaWidget from '../components/shared/CaptchaWidget';
import { Button } from '@/components/ui/button';
import { Mail, Phone, Calendar, ArrowRight, CheckCircle } from 'lucide-react';
import { useAuth } from '@/App';
import axios from 'axios';
import { toast } from 'sonner';

import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
const ContactPage = () => {
 const { t } = useTranslation();
 const { API } = useAuth();
 const [form, setForm] = useState({ name: '', email: '', company: '', message: '' });
 const [captchaToken, setCaptchaToken] = useState('');
 const [sending, setSending] = useState(false);
 const [sent, setSent] = useState(false);

 const handleSubmit = async (e) => {
 e.preventDefault();
 if (!form.name || !form.email || !form.message) return;
 if (!captchaToken) {
 notify.error('Please complete the anti-bot check below');
 return;
 }
 setSending(true);
 try {
 await axios.post(`${API}/contact`, {
 ...form,
 cf_turnstile_response: captchaToken,
 });
 setSent(true);
 notify.success(t('contact_page.success'));
 } catch (err) {
 notifyApiError(notify, err, 'Failed to send message');
 }
 setSending(false);
 };

 return (
 <div className="min-h-screen bg-[var(--color-ink-alt)]">
 <Navbar />
 
 <section className="pt-32 pb-20 px-4" data-testid="contact-hero">
 <div className="max-w-7xl mx-auto text-center">
 <span className="text-xs tracking-[0.2em] uppercase font-bold text-[var(--color-brand-blue)]" data-testid="contact-overline">{t('contact_page.overline')}</span>
 <h1 className="text-5xl sm:text-6xl tracking-tight font-bold text-white mt-4 mb-6" data-testid="contact-title">
 {t('contact_page.title')}
 </h1>
 <p className="text-base lg:text-lg leading-relaxed text-[var(--color-text-muted)] max-w-2xl mx-auto" data-testid="contact-subtitle">
 {t('contact_page.subtitle')}
 </p>
 </div>
 </section>

 <section className="py-16 px-4">
 <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-12">
 {/* Contact Form */}
 <div className="bg-[var(--theme-surface)] border border-white/10 rounded-lg p-8" data-testid="contact-form-card">
 <h2 className="text-xl font-semibold text-white mb-6">{t('contact_page.form_title')}</h2>
 {sent ? (
 <div className="text-center py-12">
 <CheckCircle className="text-green-400 mx-auto mb-4" size={40} />
 <p className="text-white font-medium">{t('contact_page.success')}</p>
 </div>
 ) : (
 <form onSubmit={handleSubmit} className="space-y-4">
 <div>
 <label className="block text-sm text-[var(--color-text-muted)] mb-1">{t('contact_page.name_label')}</label>
 <input type="text" value={form.name} onChange={e => setForm({...form, name: e.target.value})} className="w-full bg-[var(--color-ink-alt)] border border-white/10 rounded-lg px-4 py-3 text-white text-sm" required />
 </div>
 <div>
 <label className="block text-sm text-[var(--color-text-muted)] mb-1">{t('contact_page.email_label')}</label>
 <input type="email" value={form.email} onChange={e => setForm({...form, email: e.target.value})} className="w-full bg-[var(--color-ink-alt)] border border-white/10 rounded-lg px-4 py-3 text-white text-sm" required />
 </div>
 <div>
 <label className="block text-sm text-[var(--color-text-muted)] mb-1">{t('contact_page.company_label')}</label>
 <input type="text" value={form.company} onChange={e => setForm({...form, company: e.target.value})} className="w-full bg-[var(--color-ink-alt)] border border-white/10 rounded-lg px-4 py-3 text-white text-sm" />
 </div>
 <div>
 <label className="block text-sm text-[var(--color-text-muted)] mb-1">{t('contact_page.message_label')}</label>
 <textarea value={form.message} onChange={e => setForm({...form, message: e.target.value})} rows={5} className="w-full bg-[var(--color-ink-alt)] border border-white/10 rounded-lg px-4 py-3 text-white text-sm" required />
 </div>
 <CaptchaWidget action="contact" onToken={setCaptchaToken} />
 <Button type="submit" className="w-full py-5" disabled={sending} data-testid="contact-submit-btn">
 {sending ? t('contact_page.sending') : t('contact_page.send')}
 </Button>
 </form>
 )}
 </div>

 {/* Info Cards */}
 <div className="space-y-6">
 <div className="bg-[var(--theme-surface)] border border-white/10 rounded-lg p-6" data-testid="contact-email-card">
 <div className="flex items-start gap-4">
 <div className="w-10 h-10 bg-[rgb(var(--rgb-brand-blue)/0.1)] rounded-lg flex items-center justify-center flex-shrink-0">
 <Mail className="text-[var(--color-brand-blue)]" size={18} />
 </div>
 <div>
 <h3 className="text-white font-semibold mb-1">{t('contact_page.email_title')}</h3>
 <p className="text-sm text-[var(--color-text-muted)]">{t('contact_page.email_coming_soon')}</p>
 <p className="text-xs text-[var(--color-text-muted)] mt-1">{t('contact_page.email_note')}</p>
 </div>
 </div>
 </div>

 <div className="bg-[var(--theme-surface)] border border-white/10 rounded-lg p-6" data-testid="contact-demo-card">
 <div className="flex items-start gap-4">
 <div className="w-10 h-10 bg-[rgb(var(--rgb-brand-blue)/0.1)] rounded-lg flex items-center justify-center flex-shrink-0">
 <Calendar className="text-[var(--color-brand-blue)]" size={18} />
 </div>
 <div>
 <h3 className="text-white font-semibold mb-1">{t('contact_page.demo_title')}</h3>
 <p className="text-sm text-[var(--color-text-muted)]">{t('contact_page.demo_desc')}</p>
 </div>
 </div>
 </div>

 <div className="bg-gradient-to-br from-[rgb(var(--rgb-brand-blue)/0.15)] to-transparent border border-[rgb(var(--rgb-brand-blue)/0.2)] rounded-lg p-8 text-center" data-testid="contact-demo-cta">
 <h3 className="text-xl font-semibold text-white mb-2">{t('contact_page.demo_cta_title')}</h3>
 <p className="text-sm text-[var(--color-text-muted)] mb-4">{t('contact_page.demo_cta_desc')}</p>
 <Button className="" data-testid="contact-demo-btn">
 {t('contact_page.demo_cta_btn')} <ArrowRight size={16} className="ml-2" />
 </Button>
 </div>
 </div>
 </div>
 </section>

 <Footer />
 </div>
 );
};

export default ContactPage;
