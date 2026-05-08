import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import axios from 'axios';
import { AlertTriangle, Clock, Shield, Send, CheckCircle, Mail, Bell } from 'lucide-react';
import { toast } from 'sonner';

import { notify } from '@/components/notifications';
const LifecycleAlertsTab = () => {
 const { t } = useTranslation();
 const { API } = useAuth();
 const [alerts, setAlerts] = useState([]);
 const [loading, setLoading] = useState(true);
 const [criticalCount, setCriticalCount] = useState(0);
 const [warningCount, setWarningCount] = useState(0);
 const [infoCount, setInfoCount] = useState(0);

 // Expiry alerts
 const [expiryAlerts, setExpiryAlerts] = useState([]);
 const [expiryLoading, setExpiryLoading] = useState(true);
 const [sendingReminders, setSendingReminders] = useState(false);
 const [sendingId, setSendingId] = useState(null);

 useEffect(() => {
 loadAlerts();
 loadExpiryAlerts();
 }, []);

 const loadAlerts = async () => {
 const token = localStorage.getItem('token');
 try {
 const response = await axios.get(`${API}/equipment/lifecycle-alerts`, {
 headers: { Authorization: `Bearer ${token}` }
 });
 setAlerts(response.data.alerts || []);
 setCriticalCount(response.data.critical_count || 0);
 setWarningCount(response.data.warning_count || 0);
 } catch (error) {
 console.error('Failed to load alerts:', error);
 } finally {
 setLoading(false);
 }
 };

 const loadExpiryAlerts = async () => {
 const token = localStorage.getItem('token');
 try {
 const response = await axios.get(`${API}/expiry-alerts`, {
 headers: { Authorization: `Bearer ${token}` }
 });
 setExpiryAlerts(response.data.alerts || []);
 setInfoCount(response.data.total || 0);
 } catch (error) {
 console.error('Failed to load expiry alerts:', error);
 } finally {
 setExpiryLoading(false);
 }
 };

 const handleSendAllReminders = async () => {
 setSendingReminders(true);
 try {
 const token = localStorage.getItem('token');
 const res = await axios.post(`${API}/expiry-alerts/send-reminders`, {}, {
 headers: { Authorization: `Bearer ${token}` }
 });
 notify.success(res.data.message);
 loadExpiryAlerts();
 } catch {
 notify.error('Failed to send reminders');
 } finally {
 setSendingReminders(false);
 }
 };

 const handleSendSingleReminder = async (equipmentId, coverageType) => {
 setSendingId(`${equipmentId}_${coverageType}`);
 try {
 const token = localStorage.getItem('token');
 await axios.post(`${API}/expiry-alerts/${equipmentId}/send-reminder`, {
 coverage_type: coverageType
 }, {
 headers: { Authorization: `Bearer ${token}` }
 });
 notify.success('Reminder sent to admin & supplier');
 loadExpiryAlerts();
 } catch {
 notify.error('Failed to send reminder');
 } finally {
 setSendingId(null);
 }
 };

 const getAlertColor = (level) => {
 if (level === 'critical') return 'bg-red-500/20 text-red-400 border-red-500/50';
 return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50';
 };

 const getAlertIcon = (level) => {
 if (level === 'critical') return <AlertTriangle className="text-red-400" size={24} />;
 return <Clock className="text-yellow-400" size={24} />;
 };

 const getUrgencyStyle = (urgency) => {
 if (urgency === 'critical') return { border: 'border-red-500/50', bg: 'bg-red-500/10', text: 'text-red-400', badge: 'bg-red-500/20 text-red-400' };
 if (urgency === 'warning') return { border: 'border-amber-500/50', bg: 'bg-amber-500/10', text: 'text-amber-400', badge: 'bg-amber-500/20 text-amber-400' };
 return { border: 'border-[rgb(var(--rgb-brand-blue)/0.3)]', bg: 'bg-[rgb(var(--rgb-brand-blue)/0.1)]', text: 'text-[var(--color-brand-blue)]', badge: 'bg-[rgb(var(--rgb-brand-blue)/0.2)] text-[var(--color-brand-blue)]' };
 };

 if (loading && expiryLoading) {
 return <div className="text-white">Loading alerts...</div>;
 }

 const urgentExpiry = expiryAlerts.filter(a => a.days_remaining <= 30);

 return (
 <div className="space-y-6" data-testid="lifecycle-alerts-tab">
 <div className="flex items-center justify-between">
 <div>
 <h2 className="text-2xl font-semibold text-white">Equipment Lifecycle Alerts</h2>
 <p className="text-[var(--color-text-muted)]">Proactive equipment replacement, maintenance, and expiry notifications</p>
 </div>
 </div>

 {/* Summary Cards */}
 <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
 <Card className="bg-red-500/10 border-red-500/30 p-6" data-testid="critical-alerts-card">
 <div className="flex items-center justify-between">
 <div>
 <p className="text-red-400 text-sm font-semibold">Critical Alerts</p>
 <p className="text-4xl font-bold text-red-400 mt-2">{criticalCount}</p>
 </div>
 <AlertTriangle className="text-red-400" size={48} />
 </div>
 </Card>

 <Card className="bg-yellow-500/10 border-yellow-500/30 p-6" data-testid="warning-alerts-card">
 <div className="flex items-center justify-between">
 <div>
 <p className="text-yellow-400 text-sm font-semibold">Warnings</p>
 <p className="text-4xl font-bold text-yellow-400 mt-2">{warningCount}</p>
 </div>
 <Clock className="text-yellow-400" size={48} />
 </div>
 </Card>

 <Card className="bg-[rgb(var(--rgb-brand-blue)/0.1)] border-[rgb(var(--rgb-brand-blue)/0.3)] p-6" data-testid="expiry-alerts-card">
 <div className="flex items-center justify-between">
 <div>
 <p className="text-[var(--color-brand-blue)] text-sm font-semibold">Expiring Coverage</p>
 <p className="text-4xl font-bold text-[var(--color-brand-blue)] mt-2">{expiryAlerts.length}</p>
 </div>
 <Shield className="text-[var(--color-brand-blue)]" size={48} />
 </div>
 </Card>
 </div>

 {/* ── Warranty/Contract Expiry Section ── */}
 {expiryAlerts.length > 0 && (
 <div data-testid="expiry-alerts-section">
 <div className="flex items-center justify-between mb-4">
 <h3 className="text-lg font-semibold text-white flex items-center gap-2">
 <Bell size={18} className="text-[var(--color-brand-blue)]" />
 Warranty & Contract Expiry Alerts
 </h3>
 {urgentExpiry.length > 0 && (
 <Button
 onClick={handleSendAllReminders}
 disabled={sendingReminders}
 className=""
 data-testid="send-all-reminders-btn"
 >
 {sendingReminders ? (
 <><span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin mr-2" /> Sending...</>
 ) : (
 <><Mail size={16} className="mr-2" /> Send All Reminders ({urgentExpiry.length})</>
 )}
 </Button>
 )}
 </div>

 <div className="space-y-3">
 {expiryAlerts.map((alert, idx) => {
 const style = getUrgencyStyle(alert.urgency);
 const isSending = sendingId === `${alert.equipment_id}_${alert.coverage_type}`;
 return (
 <Card key={idx} className={`border p-4 ${style.border} ${style.bg}`} data-testid={`expiry-alert-${idx}`}>
 <div className="flex items-center justify-between flex-wrap gap-3">
 <div className="flex items-center gap-3 flex-1 min-w-0">
 <Shield size={20} className={style.text} />
 <div className="min-w-0">
 <div className="flex items-center gap-2 flex-wrap">
 <span className="text-white font-semibold">{alert.equipment_name}</span>
 <Badge className={style.badge}>
 {alert.coverage_type === 'warranty' ? 'Warranty' : 'Contract'}
 </Badge>
 <Badge className={style.badge} data-testid={`expiry-days-${idx}`}>
 {alert.days_remaining}d remaining
 </Badge>
 </div>
 <p className="text-[var(--color-text-muted)] text-sm">
 {alert.equipment_type}
 {alert.serial_number ? ` | S/N: ${alert.serial_number}` : ''}
 {alert.manufacturer ? ` | ${alert.manufacturer}` : ''}
 {' | Expires: '}{alert.expiry_date?.slice(0, 10)}
 </p>
 {alert.last_notified && (
 <p className="text-green-400 text-xs mt-1 flex items-center gap-1">
 <CheckCircle size={10} /> Last reminded: {new Date(alert.last_notified).toLocaleDateString()}
 {alert.notified_supplier && alert.notified_supplier !== 'none found' && (
 <span className="text-[var(--color-text-muted)]"> (Supplier: {alert.notified_supplier})</span>
 )}
 </p>
 )}
 </div>
 </div>
 <Button
 size="sm"
 onClick={() => handleSendSingleReminder(alert.equipment_id, alert.coverage_type)}
 disabled={isSending}
 className="bg-white/10 hover:bg-white/20 text-white border border-white/10"
 data-testid={`send-reminder-${idx}`}
 >
 {isSending ? 'Sending...' : <><Send size={14} className="mr-1" /> Send Reminder</>}
 </Button>
 </div>
 </Card>
 );
 })}
 </div>
 </div>
 )}

 {expiryAlerts.length === 0 && !expiryLoading && (
 <Alert className="bg-[var(--theme-surface)] border-[rgb(var(--rgb-brand-blue)/0.2)]" data-testid="no-expiry-alerts">
 <AlertDescription className="text-[var(--color-text-muted)]">
 No warranties or contracts expiring within 90 days. All coverage is up to date.
 </AlertDescription>
 </Alert>
 )}

 {/* ── Lifecycle Alerts Section ── */}
 <div className="space-y-4">
 {alerts.length > 0 && (
 <h3 className="text-lg font-semibold text-white">Equipment Lifecycle Alerts</h3>
 )}
 {alerts.map(alert => (
 <Card key={alert.equipment_id} className={`border p-6 ${getAlertColor(alert.alert_level)}`} data-testid={`alert-${alert.equipment_id}`}>
 <div className="flex items-start space-x-4">
 {getAlertIcon(alert.alert_level)}
 <div className="flex-1">
 <div className="flex items-center justify-between mb-2">
 <h3 className="text-xl font-semibold text-white">{alert.equipment_name}</h3>
 <Badge className={alert.alert_level === 'critical' ? 'bg-red-500 text-white' : 'bg-yellow-500 text-black'}>
 {alert.alert_level.toUpperCase()}
 </Badge>
 </div>
 <p className="text-white mb-2">{alert.message}</p>
 <p className="text-sm text-[var(--color-text-muted)] mb-3">Type: {alert.equipment_type}</p>
 <div className="grid grid-cols-3 gap-4 mb-4 p-3 bg-black/30 rounded-lg">
 <div>
 <p className="text-[var(--color-text-muted)] text-xs">Days in Service</p>
 <p className="text-white font-bold">{alert.stats?.days_in_service || 'N/A'}</p>
 </div>
 <div>
 <p className="text-[var(--color-text-muted)] text-xs">Total Issues</p>
 <p className="text-white font-bold">{alert.stats?.total_issues || 0}</p>
 </div>
 <div>
 <p className="text-[var(--color-text-muted)] text-xs">Open Issues</p>
 <p className="text-white font-bold">{alert.stats?.open_issues || 0}</p>
 </div>
 </div>
 <div className="bg-black/30 rounded-lg p-3">
 <p className="text-white font-semibold text-sm mb-2">Recommendations:</p>
 <ul className="space-y-1">
 {alert.recommendations.map((rec, idx) => (
 <li key={idx} className="text-sm text-[var(--color-text-muted)] flex items-start">
 <span className="text-[var(--color-brand-blue)] mr-2">•</span>
 {rec}
 </li>
 ))}
 </ul>
 </div>
 </div>
 </div>
 </Card>
 ))}

 {alerts.length === 0 && !loading && (
 <Alert className="bg-[var(--theme-surface)] border-white/10">
 <AlertDescription className="text-white">
 All equipment is within normal lifecycle parameters. No alerts at this time.
 </AlertDescription>
 </Alert>
 )}
 </div>
 </div>
 );
};

export default LifecycleAlertsTab;
