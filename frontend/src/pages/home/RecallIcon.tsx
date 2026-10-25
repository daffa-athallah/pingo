import type { ReactNode } from 'react'
import type { RecallCategory } from '../../types/recall'

type IconName = RecallCategory | 'back' | 'chevron' | 'evidence' | 'target' | 'profile'

// Small shared visual vocabulary for Daffa's Home → Category → Entity flow.
export default function RecallIcon({ name, className = '' }: { name: IconName; className?: string }) {
  const paths: Record<IconName, ReactNode> = {
    food: <><path d="M5 3v6m3-6v6M2 3v6c0 3 6 3 6 0M5 12v9M17 21V3c-4 2-5 9 0 9" /></>,
    shopping: <><path d="M5 8h14l1 13H4L5 8Zm4 0V6a3 3 0 0 1 6 0v2M9 12v1m6-1v1" /></>,
    travel: <><path d="m21 3-7 18-3-8-8-3L21 3Zm0 0L11 13" /></>,
    back: <path d="m15 5-7 7 7 7" />,
    chevron: <path d="m9 6 6 6-6 6" />,
    evidence: <><rect x="8" y="8" width="12" height="13" rx="2" /><path d="M16 8V3H3v13h5" /></>,
    target: <><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3" /><path d="M12 1v5m0 12v5M1 12h5m12 0h5" /></>,
    profile: <><circle cx="12" cy="8" r="3" /><path d="M5 21v-2a7 7 0 0 1 14 0v2" /></>,
  }
  return <svg className={className} width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>
}
