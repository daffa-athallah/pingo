import { useEffect, useState } from 'react'
import type { RecallEntity } from '../types/recall'
import RecallIcon from '../pages/home/RecallIcon'

const LABEL = (entity: RecallEntity) => (entity.category === 'food' ? 'A place to try' : entity.category === 'shopping' ? 'Something you saved' : 'Somewhere to go')

/** The card cover: a verified catalogue photo if there is one, otherwise a crop of the person's own screenshot under a warm tint with the category
 *  icon and label, otherwise just the neutral icon. Sensitive screenshots never reach here (the backend does not list them). */
export default function CatalogueImage({ entity, className }: { entity: RecallEntity; className: string }) {
  const image = entity.catalogueImage
  const shot = className.includes('entity-detail-hero') ? undefined : entity.screenshots?.[0]  // the detail page shows the screenshots themselves right below
  const [failed, setFailed] = useState(false)
  const [shotFailed, setShotFailed] = useState(false)
  useEffect(() => setFailed(false), [image?.url])
  useEffect(() => setShotFailed(false), [shot?.thumbUrl])
  if (image && !failed) return <img className={className} src={image.url} alt={image.alt}
    style={{ objectPosition: image.objectPosition }} onError={() => setFailed(true)} />
  if (shot && !shotFailed) return <span className={`${className} catalogue-shot`} role="img" aria-label={`${LABEL(entity)}: your saved screenshot`}>
    <img src={shot.thumbUrl} alt="" loading="lazy" onError={() => setShotFailed(true)} />
    <span className="catalogue-shot-tint" aria-hidden="true" />
    <span className="catalogue-shot-label"><RecallIcon name={entity.category} /><span>{LABEL(entity)}</span></span>
  </span>
  return <span className={`${className} catalogue-placeholder`} role="img" aria-label={`No verified ${entity.category === 'travel' ? 'destination' : entity.category} photo available`}>
    <RecallIcon name={entity.category} /><span>{LABEL(entity)}</span>
  </span>
}
