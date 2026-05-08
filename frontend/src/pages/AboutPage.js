import React from 'react';
import { useTranslation } from 'react-i18next';
import Navbar from '../components/shared/Navbar';
import Footer from '../components/shared/Footer';
import { Building2, Target, Award, Zap, Shield, HeartHandshake, Lightbulb } from 'lucide-react';

const AboutPage = () => {
 const { t } = useTranslation();

 return (
 <div className="min-h-screen bg-[var(--color-ink-alt)]">
 <Navbar />
 
 <section className="pt-32 pb-20 px-4" data-testid="about-hero">
 <div className="max-w-7xl mx-auto text-center">
 <span className="text-xs tracking-[0.2em] uppercase font-bold text-[var(--color-brand-blue)]" data-testid="about-overline">{t('about_page.overline')}</span>
 <h1 className="text-5xl sm:text-6xl tracking-tight font-bold text-white mt-4 mb-6" data-testid="about-title">
 {t('about_page.title')}
 </h1>
 <p className="text-base lg:text-lg leading-relaxed text-[var(--color-text-muted)] max-w-2xl mx-auto" data-testid="about-subtitle">
 {t('about_page.subtitle')}
 </p>
 </div>
 </section>

 {/* Mission Cards */}
 <section className="py-16 px-4">
 <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-6">
 {[
 { icon: Target, title: t('about_page.mission_title'), desc: t('about_page.mission_desc') },
 { icon: Building2, title: t('about_page.expertise_title'), desc: t('about_page.expertise_desc') },
 { icon: Award, title: t('about_page.trust_title'), desc: t('about_page.trust_desc') },
 ].map((item, i) => (
 <div key={i} className="bg-[var(--theme-surface)] border border-white/10 rounded-lg p-8" data-testid={`about-card-${i}`}>
 <div className="w-12 h-12 bg-[rgb(var(--rgb-brand-blue)/0.1)] rounded-lg flex items-center justify-center mb-4">
 <item.icon className="text-[var(--color-brand-blue)]" size={22} />
 </div>
 <h3 className="text-lg font-semibold text-white mb-3">{item.title}</h3>
 <p className="text-sm leading-relaxed text-[var(--color-text-muted)]">{item.desc}</p>
 </div>
 ))}
 </div>
 </section>

 {/* Story */}
 <section className="py-16 px-4 bg-[var(--theme-surface)]">
 <div className="max-w-3xl mx-auto">
 <h2 className="text-3xl font-semibold text-white mb-6">{t('about_page.story_title')}</h2>
 <div className="space-y-4 text-[var(--color-text-muted)] leading-relaxed">
 <p>{t('about_page.story_p1')}</p>
 <p>{t('about_page.story_p2')}</p>
 <p>{t('about_page.story_p3')}</p>
 </div>
 </div>
 </section>

 {/* Values */}
 <section className="py-16 px-4">
 <div className="max-w-7xl mx-auto">
 <h2 className="text-3xl font-semibold text-white mb-8 text-center">{t('about_page.values_title')}</h2>
 <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
 {[
 { icon: Zap, title: t('about_page.efficiency_title'), desc: t('about_page.efficiency_desc') },
 { icon: Shield, title: t('about_page.reliability_title'), desc: t('about_page.reliability_desc') },
 { icon: HeartHandshake, title: t('about_page.support_title'), desc: t('about_page.support_desc') },
 { icon: Lightbulb, title: t('about_page.innovation_title'), desc: t('about_page.innovation_desc') },
 ].map((v, i) => (
 <div key={i} className="bg-[var(--theme-surface)] border border-white/10 rounded-lg p-6 text-center" data-testid={`about-value-${i}`}>
 <div className="w-10 h-10 bg-[rgb(var(--rgb-brand-blue)/0.1)] rounded-lg flex items-center justify-center mx-auto mb-3">
 <v.icon className="text-[var(--color-brand-blue)]" size={18} />
 </div>
 <h4 className="text-sm font-semibold text-white mb-2">{v.title}</h4>
 <p className="text-xs leading-relaxed text-[var(--color-text-muted)]">{v.desc}</p>
 </div>
 ))}
 </div>
 </div>
 </section>

 <Footer />
 </div>
 );
};

export default AboutPage;
