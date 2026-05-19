/**
 * Shared Studio Vocab context + helpers so every piece of member-portal
 * copy can swap "member" → "athlete" / "dancer" / "swimmer" etc. based
 * on the studio_industry preset configured by the operator.
 *
 * The MemberPortal loads `/api/member/studio/vocabulary` once and pipes
 * the payload through this context so descendants don't need prop
 * drilling. Every consumer gets safe `member`/`members` fallbacks when
 * the API hasn't responded yet (or the org predates the vocab feature).
 *
 * Vocabulary shape (from the backend):
 *   { member_singular, member_plural, guardian_noun, label, ... }
 */
import { createContext, useContext, useMemo } from 'react';

const DEFAULT_VOCAB = {
  member_singular: 'member',
  member_plural: 'members',
  guardian_noun: 'guardian',
  label: 'Studio',
};

const VocabContext = createContext(DEFAULT_VOCAB);

export function StudioVocabProvider({ vocab, children }) {
  const value = useMemo(() => ({ ...DEFAULT_VOCAB, ...(vocab || {}) }), [vocab]);
  return <VocabContext.Provider value={value}>{children}</VocabContext.Provider>;
}

export function useStudioVocab() {
  return useContext(VocabContext);
}

/** Capitalize the first letter of a noun (display-only — leaves the rest
 * of the word alone so "athletes" → "Athletes" and "pre-school kids"
 * stays "Pre-school kids"). Safe on undefined input. */
export function capNoun(s) {
  if (!s) return s;
  return s.charAt(0).toUpperCase() + s.slice(1);
}
