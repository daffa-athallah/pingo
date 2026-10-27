interface Props {
  className?: string
  title?: string
}

/** Supplied V2 transparent master; preserve its original silhouette and shading. */
export default function PingoMark({ className = '', title }: Props) {
  return <img className={className} src="/brand/production/pingo-symbol-transparent.png" width="276" height="300" alt={title ?? ''} aria-hidden={title ? undefined : true} />
}
