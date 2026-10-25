type IconName = 'shopping' | 'food' | 'destination' | 'check' | 'close' | 'message'

export default function CheckInIcon({ name }: { name: IconName }) {
  return <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {name === 'shopping' && <><path d="M5 8h14l1 13H4L5 8Z" /><path d="M8 9V6a4 4 0 0 1 8 0v3" /></>}
    {name === 'food' && <><path d="M5 3v6a3 3 0 0 0 6 0V3M8 3v18M19 21V3c-3 2-4 5-4 9h4" /></>}
    {name === 'destination' && <><path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z" /><circle cx="12" cy="10" r="2.5" /></>}
    {name === 'check' && <path d="m5 12 4.5 4.5L19 7" />}
    {name === 'close' && <path d="m6 6 12 12M6 18 18 6" />}
    {name === 'message' && <><path d="M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-7l-5 3v-3H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z" /><path d="M7 11h.01M12 11h.01M17 11h.01" /></>}
  </svg>
}
