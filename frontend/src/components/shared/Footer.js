import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/App';

const FooterLink = ({ to, children, style, ...rest }) => {
  const navigate = useNavigate();
  return (
    <a
      href={to}
      onClick={(e) => { e.preventDefault(); navigate(to); window.scrollTo(0, 0); }}
      className="block text-sm text-[var(--color-text-muted)] hover:text-white transition-colors"
      style={style}
      {...rest}
    >
      {children}
    </a>
  );
};

const Footer = () => {
  const { t } = useTranslation();
  const auth = useAuth();
  const isPulse = auth?.user?.account_type === 'pulse_pro' || auth?.user?.account_type === 'lite';
  const brand = isPulse ? 'Pulse Fitness' : 'Pulse Fitness AI';

  return (
    <footer className="bg-[var(--theme-surface)] py-12 px-4" style={{ background: 'var(--theme-surface)' }}>
      <div className="max-w-7xl mx-auto">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 pb-8 border-b border-white/10" style={{ borderColor: 'var(--theme-border)' }}>
          <div>
            <h3 className="text-xl font-bold text-white mb-3" style={{ color: 'var(--theme-text)' }}>{brand}</h3>
            <p className="text-sm text-[var(--color-text-muted)]" style={{ color: 'var(--theme-text-muted)' }}>{t('footer.tagline')}</p>
          </div>
          <div>
            <h4 className="text-sm font-semibold text-white mb-3" style={{ color: 'var(--theme-text)' }}>{t('footer.company')}</h4>
            <div className="space-y-2">
              <FooterLink to="/about" style={{ color: 'var(--theme-text-muted)' }}>{t('footer.about')}</FooterLink>
              <FooterLink to="/pricing" style={{ color: 'var(--theme-text-muted)' }}>{t('nav.pricing')}</FooterLink>
              <FooterLink to="/contact" style={{ color: 'var(--theme-text-muted)' }}>{t('nav.contact')}</FooterLink>
            </div>
          </div>
          <div>
            <h4 className="text-sm font-semibold text-white mb-3" style={{ color: 'var(--theme-text)' }}>{t('nav.features')}</h4>
            <div className="space-y-2">
              <FooterLink to="/features" style={{ color: 'var(--theme-text-muted)' }}>{t('home.feat_ai_title')}</FooterLink>
              <FooterLink to="/features" style={{ color: 'var(--theme-text-muted)' }}>{t('home.feat_qr_title')}</FooterLink>
              <FooterLink to="/features" style={{ color: 'var(--theme-text-muted)' }}>{t('home.feat_warranty_title')}</FooterLink>
              <FooterLink to="/developers" style={{ color: 'var(--theme-text-muted)' }}>{t('nav.api_docs')}</FooterLink>
            </div>
          </div>
        </div>
        <div className="pt-6 text-center space-y-2">
          <div className="flex items-center justify-center gap-4 text-xs flex-wrap">
            <FooterLink to="/privacy" style={{ color: 'var(--theme-text-muted)' }}>Privacy Policy</FooterLink>
            <span className="text-[var(--color-text-muted)]" style={{ color: 'var(--theme-text-muted)' }}>|</span>
            <FooterLink to="/terms" style={{ color: 'var(--theme-text-muted)' }}>Terms of Service</FooterLink>
            <span className="text-[var(--color-text-muted)]" style={{ color: 'var(--theme-text-muted)' }}>|</span>
            <FooterLink to="/refunds" style={{ color: 'var(--theme-text-muted)' }} data-testid="footer-refund-link">
              Refund &amp; cancellation
            </FooterLink>
            <span className="text-[var(--color-text-muted)]" style={{ color: 'var(--theme-text-muted)' }}>|</span>
            <FooterLink to="/security" style={{ color: 'var(--theme-text-muted)' }} data-testid="footer-security-link">
              Security &amp; Trust
            </FooterLink>
            <span className="text-[var(--color-text-muted)]" style={{ color: 'var(--theme-text-muted)' }}>|</span>
            <FooterLink to="/trust" style={{ color: 'var(--theme-text-muted)' }} data-testid="footer-trust-link">
              Trust posture
            </FooterLink>
            <span className="text-[var(--color-text-muted)]" style={{ color: 'var(--theme-text-muted)' }}>|</span>
            <FooterLink to="/legal/dpa" style={{ color: 'var(--theme-text-muted)' }} data-testid="footer-dpa-link">
              DPA
            </FooterLink>
            <span className="text-[var(--color-text-muted)]" style={{ color: 'var(--theme-text-muted)' }}>|</span>
            <FooterLink to="/sla" style={{ color: 'var(--theme-text-muted)' }} data-testid="footer-sla-link">
              SLA
            </FooterLink>
            <span className="text-[var(--color-text-muted)]" style={{ color: 'var(--theme-text-muted)' }}>|</span>
            <FooterLink to="/sub-processors" style={{ color: 'var(--theme-text-muted)' }} data-testid="footer-subprocessors-link">
              Sub-processors
            </FooterLink>
            <span className="text-[var(--color-text-muted)]" style={{ color: 'var(--theme-text-muted)' }}>|</span>
            <FooterLink to="/status" style={{ color: 'var(--theme-text-muted)' }} data-testid="footer-status-link">
              Status
            </FooterLink>
          </div>
          <p className="text-xs text-[var(--color-text-muted)]" style={{ color: 'var(--theme-text-muted)' }}>{t('footer.copyright')}</p>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
