// Severity & status colour helpers shared across DashboardPage and its dialogs.

export const getSeverityColor = (severity) => {
  switch (severity) {
    case 'operational_minor': return 'bg-green-500/20 text-green-400';
    case 'operational_fault': return 'bg-yellow-500/20 text-yellow-400';
    case 'limited_use':       return 'bg-orange-500/20 text-orange-400';
    case 'out_of_order':      return 'bg-red-500/20 text-red-400';
    case 'safety_critical':   return 'bg-red-700/20 text-red-300';
    case 'low':               return 'bg-green-500/20 text-green-400';
    case 'medium':            return 'bg-yellow-500/20 text-yellow-400';
    case 'critical':          return 'bg-red-500/20 text-red-400';
    default:                  return 'bg-gray-500/20 text-gray-400';
  }
};

const SEVERITY_LABELS = {
  operational_minor: 'Operational - Minor Issue',
  operational_fault: 'Operational - Fault Present',
  limited_use: 'Limited Use',
  out_of_order: 'Out of Order',
  safety_critical: 'Safety Critical',
  low: 'Operational - Minor Issue',
  medium: 'Operational - Fault Present',
  critical: 'Out of Order',
};

export const getSeverityLabel = (severity) => SEVERITY_LABELS[severity] || severity;

export const getStatusColor = (status) => {
  switch (status) {
    case 'open':        return 'bg-red-500/20 text-red-400';
    case 'in_progress': return 'bg-yellow-500/20 text-yellow-400';
    case 'resolved':    return 'bg-green-500/20 text-green-400';
    default:            return 'bg-gray-500/20 text-gray-400';
  }
};
