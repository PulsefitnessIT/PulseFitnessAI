import React from 'react';

/**
 * Skeleton loader that matches the visual rhythm of a content row.
 * Much nicer than a spinner because the user sees the layout immediately.
 */
export const SkeletonLine = ({ className = '', width = '100%' }) => (
  <div
    className={`h-3 rounded-md bg-zinc-200/70 dark:bg-white/5 animate-pulse ${className}`}
    style={{ width }}
  />
);

export const SkeletonCircle = ({ size = 36, className = '' }) => (
  <div
    className={`rounded-full bg-zinc-200/70 dark:bg-white/5 animate-pulse ${className}`}
    style={{ width: size, height: size }}
  />
);

export const SkeletonCard = ({ children, className = '' }) => (
  <div className={`bg-white dark:bg-zinc-900 dark:bg-[var(--theme-surface)] border border-zinc-200 dark:border-zinc-800 dark:border-white/10 rounded-lg p-4 ${className}`}>
    {children}
  </div>
);

/** Canonical "org row" skeleton — matches AdminOrganizations layout */
export const OrgRowSkeleton = () => (
  <SkeletonCard className="border-l-[3px] border-l-zinc-200">
    <div className="flex items-center gap-4">
      <SkeletonCircle size={36} />
      <div className="flex-1 space-y-2">
        <SkeletonLine width="180px" />
        <SkeletonLine width="120px" className="h-2.5" />
      </div>
      <SkeletonLine width="60px" />
      <SkeletonLine width="60px" />
      <SkeletonLine width="90px" />
      <SkeletonLine width="110px" />
    </div>
  </SkeletonCard>
);

/** Canonical "equipment card" skeleton */
export const EquipmentCardSkeleton = () => (
  <div className="bg-[var(--theme-surface)] border-l-4 border-zinc-700 p-6 rounded-md">
    <div className="flex items-start justify-between">
      <div className="flex-1 space-y-3">
        <div className="flex items-center gap-3">
          <SkeletonLine width="240px" className="h-5" />
          <SkeletonLine width="80px" className="h-5" />
        </div>
        <div className="grid grid-cols-4 gap-4 mt-4">
          {[1,2,3,4].map(i => (
            <div key={i} className="space-y-1.5">
              <SkeletonLine width="60%" className="h-2" />
              <SkeletonLine width="85%" className="h-3" />
            </div>
          ))}
        </div>
      </div>
    </div>
  </div>
);

export default SkeletonLine;
