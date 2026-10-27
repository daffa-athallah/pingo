import { useEffect, useState } from 'react'
import type { RecallEntity } from '../types/recall'
import RecallIcon from '../pages/home/RecallIcon'

export default function CatalogueImage({ entity, className }: { entity: RecallEntity; className: string }) {
  const image = entity.catalogueImage
  const [failed, setFailed] = useState(false)
  useEffect(() => setFailed(false), [image?.url])
  if (image && !failed) return <img className={className} src={image.url} alt={image.alt}
    style={{ objectPosition: image.objectPosition }} onError={() => setFailed(true)} />
  return <span className={`${className} catalogue-placeholder`} role="img" aria-label={`No verified ${entity.category === 'travel' ? 'destination' : entity.category} photo available`}>
    <RecallIcon name={entity.category} /><span>{entity.category === 'food' ? 'A place to try' : entity.category === 'shopping' ? 'Something you saved' : 'Somewhere to go'}</span>
  </span>
}
