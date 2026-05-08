/**
 * White-label member-app wrapper.
 *
 * Mounted at /m/:slug — pulls the gym slug from the URL and passes it into
 * the shared MemberPortal. The portal then fetches branding from
 * /api/m/{slug}/branding and themes itself (logo, accent colour, gym name).
 */
import React from 'react';
import { useParams } from 'react-router-dom';
import MemberPortal from './MemberPortal';

export default function BrandedMemberApp() {
  const { slug } = useParams();
  return <MemberPortal slug={slug} />;
}
