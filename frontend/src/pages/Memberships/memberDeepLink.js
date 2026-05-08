/**
 * Member deep-link helper.
 *
 * Single source of truth for opening the member edit drawer from anywhere
 * in the app: CRM contact cards, marketing campaign rosters, gym-floor
 * dashboards, billing invoices, etc.
 *
 * The actual drawer lives inside `<MembershipsConsole/>` and listens for
 * the URL hash `#member/<id>`. Anchors built with `memberDeepLinkHref(id)`
 * navigate to `/memberships#member/<id>` so the listener picks it up.
 *
 * Usage:
 *   <Link to={memberDeepLinkHref(member.id)}>{member.name}</Link>
 *   // or imperative:
 *   openMember(member.id, navigate);
 */

export function memberDeepLinkHref(memberId) {
  if (!memberId) return '/memberships';
  return `/memberships#member/${encodeURIComponent(memberId)}`;
}

export function openMember(memberId, navigate) {
  if (!memberId) return;
  // If we're already inside Memberships, just update the hash so the
  // existing listener fires without an unnecessary route remount.
  if (typeof window !== 'undefined' && window.location.pathname.startsWith('/memberships')) {
    window.location.hash = `member/${encodeURIComponent(memberId)}`;
    return;
  }
  if (navigate) {
    navigate(memberDeepLinkHref(memberId));
  } else if (typeof window !== 'undefined') {
    window.location.href = memberDeepLinkHref(memberId);
  }
}

export default openMember;
