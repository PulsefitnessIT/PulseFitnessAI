import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import axios from 'axios';
import { notify } from '@/components/notifications';
import { Mail, BarChart3, AlertCircle, CheckCircle, Activity } from 'lucide-react';
import HelpHint from '@/components/HelpHint';

const getSeverityClass = (severity) => {
 if (severity === 'critical') return 'bg-red-500/20 text-red-400';
 if (severity === 'medium') return 'bg-yellow-500/20 text-yellow-400';
 return 'bg-green-500/20 text-green-400';
};

const WeeklyDigest = () => {
 const { t } = useTranslation();
 const { API } = useAuth();
 const [digest, setDigest] = useState(null);
 const [loading, setLoading] = useState(true);
 const [sending, setSending] = useState(false);

 const loadDigest = useCallback(async () => {
 const token = localStorage.getItem('token');
 try {
 const res = await axios.get(`${API}/digest/preview`, {
 headers: { Authorization: `Bearer ${token}` }
 });
 setDigest(res.data);
 } catch (error) {
 console.error('Failed to load digest:', error);
 } finally {
 setLoading(false);
 }
 }, [API]);

 useEffect(() => { loadDigest(); }, [loadDigest]);

 const handleSend = async () => {
 setSending(true);
 const token = localStorage.getItem('token');
 try {
 const res = await axios.post(`${API}/digest/send`, {}, {
 headers: { Authorization: `Bearer ${token}` }
 });
 if (res.data.sent) {
 notify.success('Weekly digest email sent');
 } else {
 notify.info(res.data.message || 'Email not configured yet');
 }
 } catch (error) {
 notify.error('Failed to send digest');
 } finally {
 setSending(false);
 }
 };

 if (loading) return <div className="text-[var(--color-text-muted)] text-center py-12">Loading digest...</div>;

 const s = digest?.summary || {};
 const healthColor = (score) => score >= 80 ? 'text-green-400' : score >= 50 ? 'text-yellow-400' : 'text-red-400';

 return (
 <div className="space-y-6" data-testid="weekly-digest">
 <div className="flex items-center justify-between">
 <div>
 <h2 className="text-2xl font-semibold text-white flex items-center gap-1.5">Weekly Maintenance Digest<HelpHint guideId="reporting-weekly-digest" testId="help-hint-weekly-digest" className="ml-1" /></h2>
 <p className="text-[var(--color-text-muted)]">{digest?.period || 'This week'}</p>
 </div>
 <Button onClick={handleSend} disabled={sending} className="" data-testid="send-digest-btn">
 <Mail size={18} className="mr-2" /> {sending ? 'Sending...' : 'Email Digest'}
 </Button>
 </div>

 {/* Summary Cards */}
 <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
 <Card className="bg-[var(--theme-surface)] border-white/10 p-5" data-testid="digest-open-issues">
 <div className="flex items-center gap-2 mb-2">
 <AlertCircle size={16} className="text-red-400" />
 <span className="text-[var(--color-text-muted)] text-xs">Open Issues</span>
 </div>
 <p className="text-2xl font-bold text-white">{s.open_issues || 0}</p>
 </Card>
 <Card className="bg-[var(--theme-surface)] border-white/10 p-5" data-testid="digest-critical">
 <div className="flex items-center gap-2 mb-2">
 <AlertCircle size={16} className="text-red-500" />
 <span className="text-[var(--color-text-muted)] text-xs">Critical</span>
 </div>
 <p className="text-2xl font-bold text-red-400">{s.critical_issues || 0}</p>
 </Card>
 <Card className="bg-[var(--theme-surface)] border-white/10 p-5" data-testid="digest-in-progress">
 <div className="flex items-center gap-2 mb-2">
 <Activity size={16} className="text-yellow-400" />
 <span className="text-[var(--color-text-muted)] text-xs">In Progress</span>
 </div>
 <p className="text-2xl font-bold text-white">{s.in_progress_issues || 0}</p>
 </Card>
 <Card className="bg-[var(--theme-surface)] border-white/10 p-5" data-testid="digest-checks">
 <div className="flex items-center gap-2 mb-2">
 <CheckCircle size={16} className="text-green-400" />
 <span className="text-[var(--color-text-muted)] text-xs">Checks Done</span>
 </div>
 <p className="text-2xl font-bold text-white">{s.check_sheets_completed || 0}</p>
 </Card>
 <Card className="bg-[var(--theme-surface)] border-white/10 p-5" data-testid="digest-health">
 <div className="flex items-center gap-2 mb-2">
 <BarChart3 size={16} className="text-[var(--color-brand-blue)]" />
 <span className="text-[var(--color-text-muted)] text-xs">Avg Health</span>
 </div>
 <p className={`text-2xl font-bold ${healthColor(s.avg_health_score || 0)}`}>{s.avg_health_score || 0}%</p>
 </Card>
 </div>

 {/* Open Issues List */}
 {(digest?.open_issues || []).length > 0 && (
 <Card className="bg-[var(--theme-surface)] border-white/10 p-6" data-testid="digest-issues-list">
 <h3 className="text-lg font-semibold text-white mb-4">Open Issues Requiring Attention</h3>
 <div className="space-y-2">
 {digest.open_issues.map((issue) => (
 <div key={issue.id || issue.serial_number} className="flex items-center justify-between p-3 bg-[var(--color-ink-alt)] border border-white/10 rounded-lg">
 <div>
 <p className="text-white font-medium">{issue.serial_number}</p>
 <p className="text-[var(--color-text-muted)] text-sm">{issue.machine_type}</p>
 </div>
 <Badge className={getSeverityClass(issue.severity)}>
 {issue.severity}
 </Badge>
 </div>
 ))}
 </div>
 </Card>
 )}

 {/* Equipment Health */}
 {(digest?.equipment_health || []).length > 0 && (
 <Card className="bg-[var(--theme-surface)] border-white/10 p-6" data-testid="digest-equipment-health">
 <h3 className="text-lg font-semibold text-white mb-4">Equipment Health Scores</h3>
 <div className="space-y-2">
 {digest.equipment_health.map((eq, idx) => (
 <div key={idx} className="flex items-center gap-4 p-3 bg-[var(--color-ink-alt)] border border-white/10 rounded-lg">
 <div className="flex-1">
 <p className="text-white font-medium">{eq.name}</p>
 <p className="text-[var(--color-text-muted)] text-sm">{eq.type}</p>
 </div>
 <div className="w-32">
 <div className="w-full bg-[var(--color-ink-navy)] rounded-full h-2">
 <div className={`h-2 rounded-full transition-all ${eq.health_score >= 80 ? 'bg-green-500' : eq.health_score >= 50 ? 'bg-yellow-500' : 'bg-red-500'}`} style={{ width: `${eq.health_score}%` }}></div>
 </div>
 </div>
 <span className={`text-sm font-bold min-w-[40px] text-right ${healthColor(eq.health_score)}`}>{eq.health_score}%</span>
 {eq.open_issues > 0 && <Badge className="bg-red-500/20 text-red-400">{eq.open_issues} issues</Badge>}
 </div>
 ))}
 </div>
 </Card>
 )}

 {/* Email Notice */}
 <Card className="bg-[rgb(var(--rgb-brand-blue)/0.1)] border-[rgb(var(--rgb-brand-blue)/0.3)] p-5">
 <p className="text-[var(--color-text-muted)] text-sm">
 <Mail size={14} className="inline mr-1" /> 
 Click"Email Digest" to send this report to your inbox. Email delivery requires a Resend API key in your environment configuration.
 </p>
 </Card>
 </div>
 );
};

export default WeeklyDigest;
