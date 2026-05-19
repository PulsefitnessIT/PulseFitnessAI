/**
 * Refund & Cancellation Policy — Iter 216be.
 *
 * Plain-English, founder-signed policy linked from:
 *   • Footer.js (alongside Privacy, Terms, Security, Trust)
 *   • TrialSignupModal.js fine-print (so prospects see it before they sign up)
 *   • TermsOfServicePage section 8 (cross-link)
 *
 * Style matches the existing PrivacyPolicyPage / TermsOfServicePage —
 * white shell, prose-like, single-column, ArrowLeft back-link.
 */
import { ArrowLeft, Mail } from 'lucide-react';

const Section = ({ title, children }) => (
  <section>
    <h2 className="text-lg font-semibold text-zinc-900 mt-8 mb-3">{title}</h2>
    <div className="space-y-3">{children}</div>
  </section>
);

const RefundPolicyPage = () => (
  <div className="min-h-screen bg-white" data-testid="refund-policy-page">
    <div className="max-w-3xl mx-auto px-6 py-16">
      <a href="/" className="inline-flex items-center gap-2 text-sm text-zinc-500 hover:text-zinc-900 mb-8">
        <ArrowLeft size={16} /> Back to home
      </a>
      <h1 className="text-3xl font-bold text-zinc-900 mb-2">Refund & cancellation policy</h1>
      <p className="text-sm text-zinc-500 mb-8">Last updated: February 2026 · Plain-English version</p>

      <div className="prose prose-zinc max-w-none text-sm leading-relaxed text-zinc-700">
        <p className="text-base text-zinc-800 font-medium">
          We want you to feel comfortable trying GymAxis. This page tells you exactly when you&apos;ll be charged, how to cancel, and how refunds work — no fine-print games.
        </p>

        <Section title="1. The 3-day free trial">
          <ul className="list-disc pl-6 space-y-1.5">
            <li><strong>No card required.</strong> The 3-day trial does not ask for payment details up front.</li>
            <li>Every module is unlocked for the trial window so you can evaluate the whole platform.</li>
            <li>If you do nothing at the end of the trial, your account simply switches to read-only — you are <strong>never auto-charged</strong>.</li>
          </ul>
        </Section>

        <Section title="2. Paid plans — cancel anytime">
          <ul className="list-disc pl-6 space-y-1.5">
            <li>Plans are billed monthly or annually via Stripe. Annual plans are charged up front, monthly plans on the same day each month.</li>
            <li>You can cancel from <strong>Settings → Billing</strong> at any time. There is no minimum term and no cancellation fee.</li>
            <li>When you cancel a monthly plan you keep access until the end of the current billing period, then the account moves to read-only.</li>
            <li>When you cancel an annual plan you keep access until the end of the term you paid for. See refund rules below.</li>
          </ul>
        </Section>

        <Section title="3. Refunds">
          <ul className="list-disc pl-6 space-y-1.5">
            <li><strong>Monthly plans:</strong> we don&apos;t pro-rate refunds for partial months — but if something is genuinely broken on our side, email us and we&apos;ll make it right.</li>
            <li><strong>Annual plans:</strong> if you cancel within the first 30 days, we refund the unused remainder of the year minus the months already used at the equivalent monthly rate. After 30 days, annual plans are non-refundable but remain active until the end of the term.</li>
            <li><strong>Service outages:</strong> if we miss our 99.9% uptime SLA in a given month, you can request a service credit equal to the affected fraction of that month&apos;s fee.</li>
            <li><strong>Mistaken or duplicate charges:</strong> always refunded in full, no questions asked. Just email us.</li>
          </ul>
        </Section>

        <Section title="4. Add-ons & one-time fees">
          <p>Onboarding services, data-import packages, custom integrations and other one-time fees are non-refundable once the work has begun. If we haven&apos;t started yet, the charge is fully refundable.</p>
        </Section>

        <Section title="5. Your data after cancellation">
          <ul className="list-disc pl-6 space-y-1.5">
            <li>You can export your data at any time from <strong>Settings → Export</strong>.</li>
            <li>After cancellation we keep your data in cold storage for <strong>90 days</strong> in case you change your mind, then delete it permanently. Backups are purged within a further 30 days.</li>
            <li>You can request immediate deletion under UK GDPR — see the <a href="/privacy" className="text-blue-600 underline">Privacy Policy</a>.</li>
          </ul>
        </Section>

        <Section title="6. How to ask">
          <p>
            Email <strong>billing@gymaxisai.com</strong> with the subject &ldquo;Refund request&rdquo; or &ldquo;Cancel my plan&rdquo; and the email on the account. We aim to reply the same business day; worst case, two business days.
          </p>
          <p className="text-zinc-500">
            <Mail size={12} className="inline mr-1" /> billing@gymaxisai.com — for everything else, see the <a href="/contact" className="text-blue-600 underline">Contact page</a>.
          </p>
        </Section>

        <Section title="7. Changes to this policy">
          <p>If we materially change this policy we&apos;ll notify active customers by email and surface a banner inside the product 14 days before the change takes effect. Older versions are kept on request.</p>
        </Section>

        <p className="mt-10 text-sm text-zinc-500 italic">
          This policy is written in plain English and supplements (but does not override) the corresponding clauses in our <a href="/terms" className="text-blue-600 underline">Terms of Service</a>.
        </p>
      </div>
    </div>
  </div>
);

export default RefundPolicyPage;
