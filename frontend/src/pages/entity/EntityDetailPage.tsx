import { Link, useParams } from 'react-router-dom'
import { categories, mockEntities } from '../../data/mockData'
import RecallIcon from '../home/RecallIcon'

// Owner: Daffa. Unknown IDs retain the safe detail placeholder.
export default function EntityDetailPage() {
  const { entityId } = useParams()
  const entity = mockEntities.find((item) => item.id === entityId)
  const categoryName = categories.find((category) => category.id === entity?.category)?.name
  return (
    <section className={`page entity-detail${entity ? '' : ' entity-detail--empty'}`}>
      {entity && <img className="entity-detail-hero" src={entity.imageUrl} alt={entity.name} />}
      <Link className="entity-detail-back" to={entity ? `/?category=${entity.category}` : '/'} aria-label={entity ? `Back to ${categoryName} on Home` : 'Back to Home'}><RecallIcon name="back" /></Link>
      <div className="entity-detail-sheet">
        <span className="entity-detail-handle" aria-hidden="true" />
        <header className="entity-detail-header"><h1>{entity?.name ?? 'Saved intention'}</h1>{entity?.location && <p>{entity.location}</p>}</header>
        <section className="entity-detail-intention" aria-labelledby="intention-heading">
          <h2 id="intention-heading"><span><RecallIcon name="target" /></span>Your intention</h2>
          <p>{entity?.inferredIntention ?? 'Intent detail will go here.'}</p>
        </section>
      </div>
    </section>
  )
}
