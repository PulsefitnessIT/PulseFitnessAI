/**
 * Iter 216d — group fault-list issues by their `job_id`.
 *
 * Each entry in the output is one of:
 *
 *   { type: 'single', issue: {...} }       // standalone issue (job_id null)
 *   { type: 'job',
 *     job_id: 'abc-...',
 *     issues: [...],                       // siblings logged together
 *     resolved_count: number,
 *     all_resolved: bool,
 *     latest_created_at: ISO,              // most-recent child for sort/header date
 *     primary: {...},                      // representative child for header copy
 *   }
 *
 * Order is preserved by the most-recent child's `created_at`, so a job
 * with one freshly-fixed machine still bubbles correctly.
 */
export function groupIssuesByJob(issues) {
  if (!Array.isArray(issues) || issues.length === 0) return [];

  const groups = new Map(); // job_id -> array of issues
  const singles = []; // pre-sort holders
  const seenSinglesIdx = new Map(); // issue.id → singles array index (to preserve creation order)

  for (const issue of issues) {
    const jid = issue.job_id;
    if (!jid) {
      seenSinglesIdx.set(issue.id, singles.length);
      singles.push(issue);
      continue;
    }
    if (!groups.has(jid)) groups.set(jid, []);
    groups.get(jid).push(issue);
  }

  // Treat a job with only one child as a singleton (cleaner UI — don't
  // wrap a 1-machine "job" in an expandable parent).
  const out = [];
  for (const [jobId, siblings] of groups.entries()) {
    if (siblings.length === 1) {
      singles.push(siblings[0]);
      continue;
    }
    const resolvedCount = siblings.filter(i => i.status === 'resolved').length;
    const latest = siblings.reduce(
      (acc, cur) => (cur.created_at && cur.created_at > acc.created_at ? cur : acc),
      siblings[0],
    );
    out.push({
      type: 'job',
      job_id: jobId,
      issues: siblings,
      resolved_count: resolvedCount,
      all_resolved: resolvedCount === siblings.length,
      latest_created_at: latest.created_at,
      primary: latest,
    });
  }
  for (const s of singles) {
    out.push({ type: 'single', issue: s });
  }

  // Sort outermost rows by latest_created_at desc — newest jobs/issues
  // float to the top regardless of grouping.
  out.sort((a, b) => {
    const aTs = a.type === 'job' ? a.latest_created_at : a.issue.created_at;
    const bTs = b.type === 'job' ? b.latest_created_at : b.issue.created_at;
    return (bTs || '').localeCompare(aTs || '');
  });
  return out;
}
