import React from 'react';
import { ShieldCheck } from 'lucide-react';

// Mirrors the MOD Service Portal footer chrome (acceptable-use notice +
// support contact + black copyright bar) so the BFPO portal matches
// top and bottom.
export default function Footer() {
  return (
    <div data-testid="bfpo-footer">
      <div className="max-w-6xl mx-auto px-4 pt-8 pb-6">
        <div className="rounded-2xl p-4 flex items-start gap-3 bg-white border border-slate-200">
          <ShieldCheck size={16} className="shrink-0 mt-0.5 text-cyan-600" />
          <p className="text-[12px] leading-relaxed text-[#505759]">
            Access is monitored and recorded. By using this portal you agree to the MOD
            acceptable-use policy. Suspected misuse must be reported to your chain of command.
            Trouble signing in or using the app? Contact your unit PTI or
            <a href="mailto:support@pulsefitness.ai" className="ml-1 font-semibold text-cyan-700 underline-offset-2 hover:underline">
              Pulse Fitness Support
            </a>.
          </p>
        </div>
      </div>
      <footer className="px-5 sm:px-10 py-5 text-white" style={{ background: '#000000' }}>
        <div className="max-w-6xl mx-auto text-[10px] uppercase font-bold tracking-[0.12em] sm:tracking-[0.28em]" style={{ color: '#A2ACAB' }}>
          © {new Date().getFullYear()} Pulse Fitness · MOD Service Portal
        </div>
      </footer>
    </div>
  );
}
