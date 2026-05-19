/**
 * Public instructor profile page.
 *
 * Route: /m/:slug/i/:instructorSlug
 * Backend: GET /api/public/studios/:slug/instructors/:instructorSlug
 *
 * Goal: a shareable marketing page that sells the instructor and their
 * upcoming classes. Works without auth — perfect for pasting on
 * Instagram / linking in email. The design leans into a warm editorial
 * vibe rather than the operator-console dashboard aesthetic: hero
 * photo, generous typography, specialty chips, upcoming class list with
 * direct booking links.
 */
import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import axios from 'axios';
import { Instagram, Link2, Globe, ArrowRight, Calendar, MapPin, Share2, Copy } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

function SocialChip({ href, label, Icon, colour }) {
  if (!href) return null;
  const url = href.startsWith('http') ? href : `https://instagram.com/${href.replace(/^@/, '')}`;
  return (
    <a href={url} target="_blank" rel="noreferrer"
       className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold"
       style={{ background: 'rgba(255,255,255,0.06)', color: colour }}
       data-testid={`instructor-social-${label.toLowerCase()}`}>
      <Icon size={12} /> {label}
    </a>
  );
}

function formatDate(iso) {
  if (!iso) return '';
  try { return new Date(iso).toLocaleString('en-GB', { weekday: 'short', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }); }
  catch { return iso; }
}

export default function PublicInstructorPage() {
  const { slug, instructorSlug } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/public/studios/${slug}/instructors/${instructorSlug}`);
        setData(r.data);
      } catch (e) {
        setErr(e.response?.data?.detail || 'Could not load profile');
      } finally { setLoading(false); }
    })();
  }, [slug, instructorSlug]);

  const share = async () => {
    const url = window.location.href;
    if (navigator.share) {
      try { await navigator.share({ url, title: data?.instructor?.name }); return; } catch { /* ignore */ }
    }
    try { await navigator.clipboard.writeText(url); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch { /* ignore */ }
  };

  if (loading) return <div style={{ background: '#0A0C10', color: '#fff', minHeight: '100vh', display: 'grid', placeItems: 'center' }}>Loading…</div>;
  if (err) return (
    <div style={{ background: '#0A0C10', color: '#fff', minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24 }}>
      <div style={{ maxWidth: 420, textAlign: 'center' }}>
        <h1 style={{ fontSize: 28, margin: 0 }}>Profile not found</h1>
        <p style={{ opacity: 0.7, marginTop: 12 }}>{err}</p>
        <Link to={`/m/${slug}`} style={{ color: '#00B2C7' }}>← Back to studio</Link>
      </div>
    </div>
  );

  const { studio, instructor, upcoming } = data;
  const primary = studio.primary_color || '#00B2C7';

  const initials = (instructor.name || '?').split(' ').map((w) => w[0]).slice(0, 2).join('').toUpperCase();

  return (
    <div style={{ background: '#0A0C10', color: '#fff', minHeight: '100vh' }} data-testid="public-instructor-page">
      {/* Top bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '18px 24px', maxWidth: 1080, margin: '0 auto' }}>
        <Link to={`/m/${slug}`} style={{ color: 'rgba(255,255,255,0.75)', textDecoration: 'none', fontSize: 12, letterSpacing: '0.22em', textTransform: 'uppercase' }}
          data-testid="instructor-back">{studio.name}</Link>
        <button onClick={share}
          style={{ background: 'rgba(255,255,255,0.06)', color: '#fff', border: 'none',
                   padding: '8px 14px', borderRadius: 999, fontSize: 12, fontWeight: 700,
                   display: 'inline-flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}
          data-testid="instructor-share">
          {copied ? <Copy size={12} /> : <Share2 size={12} />}
          {copied ? 'Copied' : 'Share'}
        </button>
      </div>

      {/* Hero */}
      <div style={{ position: 'relative', maxWidth: 1080, margin: '0 auto', padding: '24px 24px 48px' }}>
        {instructor.hero_photo_url && (
          <div style={{
            position: 'absolute', inset: 0,
            background: `url(${instructor.hero_photo_url}) center/cover`,
            opacity: 0.22, borderRadius: 18, filter: 'blur(2px)',
          }} />
        )}
        <div style={{ position: 'relative', display: 'grid', gridTemplateColumns: 'auto 1fr', gap: 32, alignItems: 'center' }}>
          {instructor.photo_url ? (
            <img src={instructor.photo_url} alt={instructor.name}
              style={{ width: 200, height: 200, borderRadius: '50%', objectFit: 'cover', border: `3px solid ${primary}` }}
              data-testid="instructor-photo" />
          ) : (
            <div style={{ width: 200, height: 200, borderRadius: '50%', background: primary,
                          display: 'grid', placeItems: 'center', fontSize: 72, fontWeight: 900, color: '#0A0C10' }}
              data-testid="instructor-photo-initials">
              {initials}
            </div>
          )}
          <div>
            <p style={{ margin: 0, fontSize: 11, letterSpacing: '0.22em', textTransform: 'uppercase',
                        opacity: 0.55 }}>Instructor</p>
            <h1 style={{ fontSize: 56, lineHeight: 1.05, margin: '8px 0 6px', fontWeight: 900, letterSpacing: '-0.02em' }}
              data-testid="instructor-name">{instructor.name}</h1>
            {instructor.headline && (
              <p style={{ margin: 0, fontSize: 20, color: primary, fontWeight: 700 }}
                data-testid="instructor-headline">{instructor.headline}</p>
            )}
            <div style={{ marginTop: 18, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {(instructor.specialties || []).map((s) => (
                <span key={s} data-testid={`instructor-specialty-${s.toLowerCase().replace(/\s+/g, '-')}`}
                  style={{ background: 'rgba(255,255,255,0.06)', color: '#fff',
                           padding: '5px 12px', borderRadius: 999, fontSize: 12, fontWeight: 700 }}>{s}</span>
              ))}
              {typeof instructor.years_experience === 'number' && instructor.years_experience > 0 && (
                <span style={{ background: primary, color: '#0A0C10',
                               padding: '5px 12px', borderRadius: 999, fontSize: 12, fontWeight: 800 }}
                  data-testid="instructor-experience">{instructor.years_experience}y teaching</span>
              )}
            </div>
            <div style={{ marginTop: 16, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              <SocialChip href={instructor.social?.instagram} label="Instagram" Icon={Instagram} colour={primary} />
              <SocialChip href={instructor.social?.tiktok}    label="TikTok"    Icon={Link2} colour={primary} />
              <SocialChip href={instructor.social?.linkedin}  label="LinkedIn"  Icon={Link2} colour={primary} />
              <SocialChip href={instructor.social?.website}   label="Website"   Icon={Globe} colour={primary} />
            </div>
          </div>
        </div>
      </div>

      {/* Bio */}
      {instructor.bio && (
        <section style={{ maxWidth: 780, margin: '0 auto', padding: '0 24px 48px' }} data-testid="instructor-bio">
          <h2 style={{ fontSize: 14, letterSpacing: '0.22em', textTransform: 'uppercase', opacity: 0.55, margin: 0 }}>About</h2>
          <p style={{ fontSize: 18, lineHeight: 1.7, whiteSpace: 'pre-wrap', marginTop: 12 }}>{instructor.bio}</p>
        </section>
      )}

      {/* Qualifications */}
      {(instructor.qualifications || []).length > 0 && (
        <section style={{ maxWidth: 780, margin: '0 auto', padding: '0 24px 48px' }} data-testid="instructor-qualifications">
          <h2 style={{ fontSize: 14, letterSpacing: '0.22em', textTransform: 'uppercase', opacity: 0.55, margin: 0 }}>Qualifications</h2>
          <ul style={{ marginTop: 12, padding: 0, listStyle: 'none' }}>
            {instructor.qualifications.map((q) => (
              <li key={q} style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '10px 0',
                                   borderBottom: '1px solid rgba(255,255,255,0.08)', fontSize: 15 }}>
                <span style={{ width: 8, height: 8, borderRadius: 999, background: primary, flex: 'none' }} />
                {q}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Upcoming classes */}
      <section style={{ maxWidth: 1080, margin: '0 auto', padding: '0 24px 64px' }}>
        <h2 style={{ fontSize: 14, letterSpacing: '0.22em', textTransform: 'uppercase', opacity: 0.55, margin: 0 }}>
          Upcoming classes
        </h2>
        {(upcoming || []).length === 0 ? (
          <p style={{ marginTop: 16, opacity: 0.55, fontSize: 14 }}>
            No classes scheduled yet. Follow the studio for updates.
          </p>
        ) : (
          <div style={{ marginTop: 16, display: 'grid', gap: 10 }} data-testid="instructor-upcoming">
            {upcoming.map((occ) => {
              const spotsLeft = Math.max((occ.capacity || 0) - (occ.bookings_count || 0), 0);
              const full = occ.capacity && spotsLeft === 0;
              return (
                <Link to={`/m/${slug}/c/${occ.id}`} key={occ.id}
                  style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 14, alignItems: 'center',
                           padding: '18px 20px', background: 'rgba(255,255,255,0.04)',
                           borderLeft: `3px solid ${primary}`, borderRadius: 12,
                           textDecoration: 'none', color: '#fff' }}
                  data-testid={`instructor-class-${occ.id}`}>
                  <div>
                    <div style={{ fontSize: 17, fontWeight: 800, marginBottom: 4 }}>{occ.name || 'Class'}</div>
                    <div style={{ fontSize: 13, opacity: 0.65, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        <Calendar size={11} /> {formatDate(occ.starts_at)}
                      </span>
                      {occ.room_name && (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                          <MapPin size={11} /> {occ.room_name}
                        </span>
                      )}
                      <span style={{ color: full ? '#f87171' : primary, fontWeight: 700 }}>
                        {full ? 'Waitlist' : `${spotsLeft} spots left`}
                      </span>
                    </div>
                  </div>
                  <ArrowRight size={18} style={{ opacity: 0.5 }} />
                </Link>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
