import { createContext, useContext } from 'react';

// Iter 282 — unsaved-work guard for Dealer Parts. A child screen (e.g. the
// Allocation Wizard) reports whether it has in-progress work via `setDirty`.
// The page uses it to warn before switching tabs, and to arm a browser
// beforeunload prompt.
export const DealerPartsNavContext = createContext({ setDirty: () => {} });

export const useDealerPartsNav = () => useContext(DealerPartsNavContext);
