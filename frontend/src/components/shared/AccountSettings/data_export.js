/**
 * Account Settings → Data export.
 *
 * Iter 216h163 — wraps the shared SiteDataExportPanel so HQ owners can
 * pull JSON / ZIP-CSV exports for any site they manage, straight from
 * the Account Settings modal.
 */
import React from 'react';
import SiteDataExportPanel from '@/pages/SiteDataExportPanel';

export default function DataExportSection() {
  return (
    <div data-testid="account-data-export-section">
      <SiteDataExportPanel />
    </div>
  );
}
