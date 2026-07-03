import { useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Eye, EyeOff, CheckCircle, Loader2, ArrowLeft } from 'lucide-react';
import { notify } from '@/components/notifications';
import axios from 'axios';
import { useAuth } from '@/App';

const ResetPasswordPage = () => {
  const { API } = useAuth();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState('');
  // Request-a-reset (no token) step
  const [email, setEmail] = useState('');
  const [reqLoading, setReqLoading] = useState(false);
  const [reqSent, setReqSent] = useState(false);
  const [reqError, setReqError] = useState('');

  const handleRequest = async (e) => {
    e.preventDefault();
    setReqLoading(true);
    setReqError('');
    try {
      await axios.post(`${API}/auth/forgot-password`, { email: email.trim().toLowerCase() });
      // Backend always returns a generic message to prevent email enumeration.
      setReqSent(true);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setReqError(typeof detail === 'string' ? detail : 'Could not send reset email. Please try again in a moment.');
    }
    setReqLoading(false);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }
    if (password.length < 6) {
      setError('Password must be at least 6 characters');
      return;
    }

    setLoading(true);
    setError('');
    try {
      await axios.post(`${API}/auth/reset-password`, { token, password });
      setSuccess(true);
      notify.success('Password reset successfully');
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to reset password. The link may have expired.');
    }
    setLoading(false);
  };

  if (!token) {
    if (reqSent) {
      return (
        <div className="min-h-screen flex items-center justify-center px-4" style={{ background: 'var(--theme-bg)' }}>
          <Card className="w-full max-w-md p-8 text-center" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
            <CheckCircle size={48} className="text-emerald-500 mx-auto mb-4" />
            <h2 className="text-xl font-bold mb-2" style={{ color: 'var(--theme-text)' }}>Check your email</h2>
            <p className="text-sm mb-6" style={{ color: 'var(--theme-text-muted)' }}>
              If an account exists for <span className="font-semibold">{email}</span>, we've sent a link to reset your password. The link expires in 15 minutes.
            </p>
            <Link to="/"><Button data-testid="reset-request-done-home">Back to Home</Button></Link>
          </Card>
        </div>
      );
    }
    return (
      <div className="min-h-screen flex items-center justify-center px-4" style={{ background: 'var(--theme-bg)' }}>
        <Card className="w-full max-w-md p-8" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
          <Link to="/" className="inline-flex items-center gap-1 text-sm mb-6 hover:opacity-80" style={{ color: 'var(--theme-text-muted)' }}>
            <ArrowLeft size={14} /> Back to Home
          </Link>
          <h2 className="text-2xl font-bold mb-1" style={{ color: 'var(--theme-text)' }}>Forgot your password?</h2>
          <p className="text-sm mb-6" style={{ color: 'var(--theme-text-muted)' }}>Enter your account email and we'll send you a link to reset it.</p>

          <form onSubmit={handleRequest} className="space-y-4" data-testid="reset-request-form">
            <div>
              <label className="text-sm font-medium mb-1 block" style={{ color: 'var(--theme-text)' }}>Email</label>
              <Input
                type="email"
                autoCapitalize="none"
                autoCorrect="off"
                spellCheck={false}
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="you@gym.com"
                required
                data-testid="reset-request-email"
              />
            </div>

            {reqError && <p className="text-sm text-red-500" data-testid="reset-request-error">{reqError}</p>}

            <Button type="submit" className="w-full" disabled={reqLoading} data-testid="reset-request-submit">
              {reqLoading ? <Loader2 size={16} className="animate-spin mr-2" /> : null}
              Send reset link
            </Button>
            <p className="text-center text-sm" style={{ color: 'var(--theme-text-muted)' }}>
              Remembered it? <Link to="/login" className="font-semibold hover:opacity-80" style={{ color: 'var(--theme-text)' }} data-testid="reset-request-back-login">Back to sign in</Link>
            </p>
          </form>
        </Card>
      </div>
    );
  }

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4" style={{ background: 'var(--theme-bg)' }}>
        <Card className="w-full max-w-md p-8 text-center" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
          <CheckCircle size={48} className="text-emerald-500 mx-auto mb-4" />
          <h2 className="text-xl font-bold mb-2" style={{ color: 'var(--theme-text)' }}>Password Reset Complete</h2>
          <p className="text-sm mb-6" style={{ color: 'var(--theme-text-muted)' }}>Your password has been changed. You can now log in with your new password.</p>
          <Link to="/login"><Button data-testid="reset-go-login">Go to Login</Button></Link>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4" style={{ background: 'var(--theme-bg)' }}>
      <Card className="w-full max-w-md p-8" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
        <Link to="/" className="inline-flex items-center gap-1 text-sm mb-6 hover:opacity-80" style={{ color: 'var(--theme-text-muted)' }}>
          <ArrowLeft size={14} /> Back to Home
        </Link>
        <h2 className="text-2xl font-bold mb-1" style={{ color: 'var(--theme-text)' }}>Reset Your Password</h2>
        <p className="text-sm mb-6" style={{ color: 'var(--theme-text-muted)' }}>Enter your new password below.</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-sm font-medium mb-1 block" style={{ color: 'var(--theme-text)' }}>New Password</label>
            <div className="relative">
              <Input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="Enter new password"
                required
                minLength={6}
                data-testid="reset-password-input"
              />
              <button type="button" onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 opacity-50 hover:opacity-100">
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <div>
            <label className="text-sm font-medium mb-1 block" style={{ color: 'var(--theme-text)' }}>Confirm Password</label>
            <Input
              type={showPassword ? 'text' : 'password'}
              value={confirmPassword}
              onChange={e => setConfirmPassword(e.target.value)}
              placeholder="Confirm new password"
              required
              minLength={6}
              data-testid="reset-confirm-input"
            />
          </div>

          {error && <p className="text-sm text-red-500" data-testid="reset-error">{error}</p>}

          <Button type="submit" className="w-full" disabled={loading} data-testid="reset-submit-btn">
            {loading ? <Loader2 size={16} className="animate-spin mr-2" /> : null}
            Reset Password
          </Button>
        </form>
      </Card>
    </div>
  );
};

export default ResetPasswordPage;
