import { Link, useParams } from 'react-router-dom'
import { categories } from '../../data/mockData'
import { useRecallEntities } from '../../data/useRecallEntities'
import RecallIcon from '../home/RecallIcon'
import CatalogueImage from '../../components/CatalogueImage'
import DeleteIntention from '../../features/demo/DeleteIntention'

// Owner: Daffa. Unknown IDs retain the safe detail placeholder.
export default function EntityDetailPage() {
  const { entityId } = useParams()
  const data = useRecallEntities()
  const entity = data.entities.find((item) => item.id === entityId)
  const categoryName = categories.find((category) => category.id === entity?.category)?.name
  return (
    <section className={`page entity-detail${entity ? '' : ' entity-detail--empty'}`}>
      {entity && <CatalogueImage className="entity-detail-hero" entity={entity} />}
      <Link className="entity-detail-back" to={entity ? `/?category=${entity.category}` : '/'} aria-label={entity ? `Back to ${categoryName} on Home` : 'Back to Home'}><RecallIcon name="back" /></Link>
      <div className="entity-detail-sheet">
        <span className="entity-detail-handle" aria-hidden="true" />
        <header className="entity-detail-header"><h1>{entity?.name ?? 'Saved intention'}</h1>{entity?.location && <p>{entity.location}</p>}</header>
        <section data-guide-target="intention" className="entity-detail-intention" aria-labelledby="intention-heading">
          <h2 id="intention-heading"><span><RecallIcon name="target" /></span>pingo’s hunch</h2>
          <p>{entity?.inferredIntention ?? (data.status === 'loading' ? 'Loading your saved thing…' : 'This saved thing is unavailable. Return to your collection and try again.')}</p>
          {entity && <small>Inferred from your saved screenshots—not a reminder you created.</small>}
        </section>
        {entity?.screenshots && entity.screenshots.length > 0 && (
          <section data-guide-target="screenshots" className="entity-detail-shots" aria-labelledby="shots-heading">
            <h2 id="shots-heading">Your saved screenshots ({entity.screenshots.length})</h2>
            <div className="entity-detail-shot-list">
              {entity.screenshots.map((shot) => (
                <a key={shot.id} href={shot.fullUrl} target="_blank" rel="noreferrer" title={shot.summary}>
                  <img src={shot.thumbUrl} alt={shot.summary} loading="lazy" />
                </a>
              ))}
            </div>
          </section>
        )}
        {entity && <DeleteIntention loopId={entity.id} name={entity.name} />}
        {entity?.catalogueImage && <p className="catalogue-credit">Catalogue photo source: {entity.catalogueImage.source}</p>}
      </div>
    </section>
  )
}
