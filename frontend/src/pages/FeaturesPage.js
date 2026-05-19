import { useTranslation } from 'react-i18next';
import Navbar from '../components/shared/Navbar';
import Footer from '../components/shared/Footer';
import { Button } from '@/components/ui/button';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Brain, QrCode, Smartphone, Shield, Bell, Camera, FileText,
  Wrench, ShoppingCart, ClipboardCheck, Layout, BarChart3,
  Users, Globe, Settings, Mail, ArrowRight, CheckCircle
} from 'lucide-react';

const FeaturesPage = () => {
  const { t } = useTranslation();

  const groups = [
    {
      label: t('features_page.group_ai'), title: t('features_page.group_ai_title'),
      features: [
        { icon: Brain, title: t('features_page.ai_diagnosis_title'), points: [t('features_page.ai_diagnosis_1'), t('features_page.ai_diagnosis_2'), t('features_page.ai_diagnosis_3'), t('features_page.ai_diagnosis_4')] },
        { icon: Smartphone, title: t('features_page.ai_triage_title'), points: [t('features_page.ai_triage_1'), t('features_page.ai_triage_2'), t('features_page.ai_triage_3'), t('features_page.ai_triage_4')] },
        { icon: Camera, title: t('features_page.ai_risk_title'), points: [t('features_page.ai_risk_1'), t('features_page.ai_risk_2'), t('features_page.ai_risk_3')] },
        { icon: FileText, title: t('features_page.ai_audit_title'), points: [t('features_page.ai_audit_1'), t('features_page.ai_audit_2'), t('features_page.ai_audit_3')] },
      ],
    },
    {
      label: t('features_page.group_qr'), title: t('features_page.group_qr_title'),
      features: [
        { icon: QrCode, title: t('features_page.qr_codes_title'), points: [t('features_page.qr_codes_1'), t('features_page.qr_codes_2'), t('features_page.qr_codes_3')] },
        { icon: ClipboardCheck, title: t('features_page.mobile_checks_title'), points: [t('features_page.mobile_checks_1'), t('features_page.mobile_checks_2'), t('features_page.mobile_checks_3'), t('features_page.mobile_checks_4')] },
        { icon: Camera, title: t('features_page.mobile_fault_title'), points: [t('features_page.mobile_fault_1'), t('features_page.mobile_fault_2'), t('features_page.mobile_fault_3'), t('features_page.mobile_fault_4')] },
      ],
    },
    {
      label: t('features_page.group_warranty'), title: t('features_page.group_warranty_title'),
      features: [
        { icon: Shield, title: t('features_page.warranty_title'), points: [t('features_page.warranty_1'), t('features_page.warranty_2'), t('features_page.warranty_3')] },
        { icon: Bell, title: t('features_page.expiry_title'), points: [t('features_page.expiry_1'), t('features_page.expiry_2'), t('features_page.expiry_3')] },
        { icon: Mail, title: t('features_page.supplier_email_title'), points: [t('features_page.supplier_email_1'), t('features_page.supplier_email_2'), t('features_page.supplier_email_3'), t('features_page.supplier_email_4')] },
      ],
    },
    {
      label: t('features_page.group_ops'), title: t('features_page.group_ops_title'),
      features: [
        { icon: Wrench, title: t('features_page.fault_title'), points: [t('features_page.fault_1'), t('features_page.fault_2'), t('features_page.fault_3'), t('features_page.fault_4')] },
        { icon: ShoppingCart, title: t('features_page.po_title'), points: [t('features_page.po_1'), t('features_page.po_2'), t('features_page.po_3'), t('features_page.po_4')] },
        { icon: Layout, title: t('features_page.layout_title'), points: [t('features_page.layout_1'), t('features_page.layout_2'), t('features_page.layout_3'), t('features_page.layout_4')] },
        { icon: BarChart3, title: t('features_page.ops_reports_title'), points: [t('features_page.ops_reports_1'), t('features_page.ops_reports_2'), t('features_page.ops_reports_3'), t('features_page.ops_reports_4')] },
      ],
    },
    {
      label: t('features_page.group_enterprise'), title: t('features_page.group_enterprise_title'),
      features: [
        { icon: Users, title: t('features_page.multiuser_title'), points: [t('features_page.multiuser_1'), t('features_page.multiuser_2'), t('features_page.multiuser_3')] },
        { icon: Globe, title: t('features_page.supplier_portal_title'), points: [t('features_page.supplier_portal_1'), t('features_page.supplier_portal_2'), t('features_page.supplier_portal_3')] },
        { icon: Settings, title: t('features_page.whitelabel_title'), points: [t('features_page.whitelabel_1'), t('features_page.whitelabel_2'), t('features_page.whitelabel_3')] },
      ],
    },
  ];

  return (
    <div className="min-h-screen bg-[var(--color-surface-darker)]">
      <Navbar />
      
      <section className="pt-32 pb-20 px-4" data-testid="features-hero">
        <div className="max-w-7xl mx-auto text-center">
          <span className="text-xs tracking-[0.25em] uppercase font-extrabold text-[var(--color-brand-cyan)]" data-testid="features-overline">{t('features_page.overline')}</span>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl tracking-tight font-extrabold text-white mt-4 mb-6" style={{ letterSpacing: '-0.03em' }} data-testid="features-title">
            {t('features_page.title')}
          </h1>
          <p className="text-base lg:text-lg leading-relaxed text-[var(--color-text-muted)] max-w-2xl mx-auto" data-testid="features-subtitle">
            {t('features_page.subtitle')}
          </p>
        </div>
      </section>

      {groups.map((group, gi) => (
        <section key={gi} className={`py-16 px-4 ${gi % 2 === 0 ? '' : 'bg-[var(--color-ink)]'}`} data-testid={`feature-group-${gi}`}>
          <div className="max-w-7xl mx-auto">
            <div className="mb-10">
              <span className="text-xs tracking-[0.2em] uppercase font-bold text-[var(--color-brand-cyan)]">{group.label}</span>
              <h2 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white mt-2" style={{ letterSpacing: '-0.02em' }}>{group.title}</h2>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {group.features.map((feat, fi) => (
                <motion.div
                  key={fi}
                  initial={{ opacity: 0, y: 15 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: fi * 0.08 }}
                  className="bg-white/[0.03] border border-white/10 rounded-xl p-6 hover:-translate-y-1 hover:border-[rgb(var(--rgb-brand-cyan)/0.4)] transition-all"
                  data-testid={`feature-card-${gi}-${fi}`}
                >
                  <div className="flex items-start gap-4">
                    <div className="w-10 h-10 bg-[rgb(var(--rgb-brand-cyan)/0.1)] rounded-lg flex items-center justify-center flex-shrink-0">
                      <feat.icon className="text-[var(--color-brand-cyan)]" size={20} />
                    </div>
                    <div className="flex-1">
                      <h3 className="text-white font-extrabold mb-3">{feat.title}</h3>
                      <ul className="space-y-2">
                        {feat.points.map((p, pi) => (
                          <li key={pi} className="flex items-start gap-2 text-sm text-[var(--color-text-muted)]">
                            <CheckCircle size={14} className="text-[var(--color-brand-cyan)] mt-0.5 flex-shrink-0" />
                            <span>{p}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          </div>
        </section>
      ))}

      {/* CTA */}
      <section className="py-24 px-4 bg-[var(--color-surface-darker)]">
        <div className="max-w-5xl mx-auto bg-gradient-to-br from-[rgb(var(--rgb-brand-cyan)/0.15)] to-transparent border border-[rgb(var(--rgb-brand-cyan)/0.2)] rounded-2xl p-12 text-center" data-testid="features-cta">
          <h2 className="text-3xl font-extrabold tracking-tight text-white mb-4" style={{ letterSpacing: '-0.025em' }}>{t('features_page.cta_title')}</h2>
          <p className="text-[var(--color-text-muted)] mb-8">{t('features_page.cta_desc')}</p>
          <Link to="/pricing">
            <Button className="bg-[var(--color-brand-cyan)] hover:brightness-110 text-[var(--color-surface-darker)] px-8 py-6 text-lg font-extrabold tracking-wider uppercase" data-testid="features-cta-btn">
              {t('nav.pricing')} <ArrowRight className="ml-2" size={20} />
            </Button>
          </Link>
        </div>
      </section>

      <Footer />
    </div>
  );
};

export default FeaturesPage;
