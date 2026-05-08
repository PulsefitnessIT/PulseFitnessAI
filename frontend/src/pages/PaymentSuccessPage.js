import React, { useEffect, useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { useAuth } from '@/App';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { CheckCircle, ArrowRight, Loader2, CreditCard, LayoutDashboard, Headphones } from 'lucide-react';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL + '/api';

const PaymentSuccessPage = () => {
  const { user } = useAuth();
  const [searchParams] = useSearchParams();
  const [payment, setPayment] = useState(null);
  const [loading, setLoading] = useState(true);

  const sessionId = searchParams.get('session_id');

  useEffect(() => {
    if (!sessionId) { setLoading(false); return; }
    const token = localStorage.getItem('token');
    if (!token) { setLoading(false); return; }

    const checkPayment = async () => {
      try {
        const res = await axios.get(`${API}/payments/status/${sessionId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        setPayment(res.data);
      } catch {
        // Session might not be found — still show generic success
      }
      setLoading(false);
    };
    checkPayment();
  }, [sessionId]);

  const isPaid = payment?.payment_status === 'paid';
  const packageName = payment?.package_name || 'GymAxis';
  const amount = payment?.amount || '';

  if (loading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="text-center">
          <Loader2 size={40} className="animate-spin text-[var(--color-brand-blue)] mx-auto mb-4" />
          <p className="text-zinc-400 text-sm">Confirming your payment...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center px-4">
      <div className="max-w-lg w-full">
        {/* Success Animation */}
        <div className="text-center mb-8">
          <div className="w-20 h-20 rounded-full bg-green-500/10 border-2 border-green-500/30 flex items-center justify-center mx-auto mb-6 animate-[pulse_2s_ease-in-out_1]">
            <CheckCircle size={40} className="text-green-500" />
          </div>
          <h1 className="text-3xl font-bold text-white mb-2">
            {isPaid ? 'Payment Successful!' : 'Thank You!'}
          </h1>
          <p className="text-zinc-400 text-base">
            {isPaid
              ? `Welcome to ${packageName}. Your subscription is now active.`
              : 'Your subscription is being processed. You\'ll have access shortly.'}
          </p>
        </div>

        {/* Payment Details Card */}
        {payment && (
          <Card className="bg-zinc-900 border-zinc-800 p-6 mb-6" data-testid="payment-details-card">
            <div className="flex items-center gap-3 mb-4 pb-4 border-b border-zinc-800">
              <CreditCard size={20} className="text-[var(--color-brand-blue)]" />
              <h2 className="text-sm font-semibold text-white">Subscription Details</h2>
            </div>
            <div className="space-y-3 text-sm">
              <div className="flex justify-between">
                <span className="text-zinc-500">Plan</span>
                <span className="text-white font-medium">{packageName}</span>
              </div>
              {amount && (
                <div className="flex justify-between">
                  <span className="text-zinc-500">Monthly price</span>
                  <span className="text-white font-medium">£{amount}/mo</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-zinc-500">Status</span>
                <span className={`font-medium ${isPaid ? 'text-green-400' : 'text-amber-400'}`}>
                  {isPaid ? 'Active' : 'Processing'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-zinc-500">Account</span>
                <span className="text-white">{user?.email || payment.user_email}</span>
              </div>
            </div>
          </Card>
        )}

        {/* What's Next */}
        <Card className="bg-zinc-900 border-zinc-800 p-6 mb-6" data-testid="whats-next-card">
          <h2 className="text-sm font-semibold text-white mb-4">What's Next</h2>
          <div className="space-y-3">
            <div className="flex gap-3 items-start">
              <div className="w-6 h-6 rounded-full bg-[rgb(var(--rgb-brand-blue)/0.2)] flex items-center justify-center shrink-0 mt-0.5">
                <span className="text-[var(--color-brand-blue)] text-xs font-bold">1</span>
              </div>
              <div>
                <p className="text-sm text-white font-medium">Set up your equipment</p>
                <p className="text-xs text-zinc-500">Import your equipment via CSV or AI-powered invoice parsing</p>
              </div>
            </div>
            <div className="flex gap-3 items-start">
              <div className="w-6 h-6 rounded-full bg-[rgb(var(--rgb-brand-blue)/0.2)] flex items-center justify-center shrink-0 mt-0.5">
                <span className="text-[var(--color-brand-blue)] text-xs font-bold">2</span>
              </div>
              <div>
                <p className="text-sm text-white font-medium">Invite your team</p>
                <p className="text-xs text-zinc-500">Add staff members so they can log faults and track maintenance</p>
              </div>
            </div>
            <div className="flex gap-3 items-start">
              <div className="w-6 h-6 rounded-full bg-[rgb(var(--rgb-brand-blue)/0.2)] flex items-center justify-center shrink-0 mt-0.5">
                <span className="text-[var(--color-brand-blue)] text-xs font-bold">3</span>
              </div>
              <div>
                <p className="text-sm text-white font-medium">Explore AI features</p>
                <p className="text-xs text-zinc-500">Use AI diagnosis, CAPEX analysis, and predictive maintenance</p>
              </div>
            </div>
          </div>
        </Card>

        {/* Action Buttons */}
        <div className="flex flex-col gap-3">
          <Link to="/dashboard">
            <Button className="w-full h-12 bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white font-medium" data-testid="go-to-dashboard">
              <LayoutDashboard size={18} className="mr-2" /> Go to Dashboard
            </Button>
          </Link>
          <Link to="/pricing">
            <Button variant="outline" className="w-full h-10 border-zinc-700 text-zinc-400 hover:text-white hover:border-zinc-500" data-testid="view-plans">
              <Headphones size={16} className="mr-2" /> Need help? Contact support
            </Button>
          </Link>
        </div>

        {/* Footer */}
        <p className="text-center text-xs text-zinc-600 mt-8">
          A receipt has been sent to your email. You can manage your subscription from the dashboard at any time.
        </p>
      </div>
    </div>
  );
};

export default PaymentSuccessPage;
