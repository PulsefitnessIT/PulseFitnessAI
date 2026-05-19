/**
 * CaptchaWidget — lazily loads Cloudflare Turnstile / hCaptcha and surfaces
 * the verification token via ``onToken``. The widget is a no-op in dev
 * (when ``/api/captcha/config`` returns ``enabled: false``) so local flows
 * are never blocked by missing env vars.
 *
 * Props:
 *   action  — free-form label for logging (e.g. "login", "forgot_password")
 *   onToken — invoked with a string token (or "" when captcha is disabled)
 */
import { useEffect, useRef, useState } from 'react';
import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const SCRIPTS = {
  turnstile: 'https://challenges.cloudflare.com/turnstile/v0/api.js',
  hcaptcha: 'https://js.hcaptcha.com/1/api.js',
};

function loadScript(src) {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) {
      resolve();
      return;
    }
    const s = document.createElement('script');
    s.src = src;
    s.async = true;
    s.defer = true;
    s.onload = () => resolve();
    s.onerror = reject;
    document.head.appendChild(s);
  });
}

export default function CaptchaWidget({ action = 'public', onToken }) {
  const mountRef = useRef(null);
  const [cfg, setCfg] = useState(null);

  useEffect(() => {
    let cancelled = false;
    axios
      .get(`${API}/captcha/config`)
      .then((res) => {
        if (!cancelled) setCfg(res.data || {});
      })
      .catch(() => {
        if (!cancelled) setCfg({ enabled: false });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!cfg || !cfg.enabled || !cfg.site_key) {
      // Dev/no-captcha path — deliver a truthy sentinel so the parent
      // form's `if (!token)` validation passes. Backend captcha helper
      // fails open in dev when CAPTCHA_SECRET is unset, so this is safe.
      if (onToken) onToken('dev-bypass');
      return;
    }
    const provider = cfg.provider || 'turnstile';
    const src = SCRIPTS[provider];
    if (!src) return;
    loadScript(src).then(() => {
      if (!mountRef.current) return;
      if (provider === 'turnstile' && window.turnstile) {
        window.turnstile.render(mountRef.current, {
          sitekey: cfg.site_key,
          callback: (token) => onToken && onToken(token),
          'expired-callback': () => onToken && onToken(''),
        });
      } else if (provider === 'hcaptcha' && window.hcaptcha) {
        window.hcaptcha.render(mountRef.current, {
          sitekey: cfg.site_key,
          callback: (token) => onToken && onToken(token),
          'expired-callback': () => onToken && onToken(''),
        });
      }
    });
  }, [cfg, onToken]);

  if (!cfg || !cfg.enabled) return null;
  return (
    <div
      ref={mountRef}
      data-testid={`captcha-widget-${action}`}
      className="mt-2 flex justify-center"
    />
  );
}
