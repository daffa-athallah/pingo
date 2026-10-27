interface Props {
  className?: string
  showTagline?: boolean
}

export default function PingoBrand({ className = '', showTagline = false }: Props) {
  return <span className={`pingo-brand ${className}`.trim()} aria-label={showTagline ? 'pingo — Your screenshots have plans.' : 'pingo'}>
    <span className="pingo-brand-lockup" aria-hidden="true">
      <img className="pingo-production-lockup" src="/brand/production/pingo-lockup-transparent.png" width="1600" height="500" alt="" />
    </span>
    {showTagline && <span className="pingo-tagline" aria-hidden="true">Your screenshots have plans.</span>}
  </span>
}
