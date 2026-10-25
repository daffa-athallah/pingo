import { Link, useParams } from 'react-router-dom'
import PageHeader from '../../components/common/PageHeader'
import { mockEntities } from '../../data/mockData'

// Owner: Daffa. Unknown entity IDs deliberately render a safe placeholder.
export default function EntityDetailPage() {
  const { entityId } = useParams()
  const entity = mockEntities.find((item) => item.id === entityId)

  return (
    <section className="page entity-detail">
      <Link className="back-link" to={entity ? `/category/${entity.category}` : '/'}>
        ← {entity ? 'Category' : 'Home'}
      </Link>
      <PageHeader title={entity?.name ?? 'Saved intention'} />
      <div className="entity-detail-card">
        <h2>Your intention</h2>
        <p>{entity?.inferredIntention ?? 'Intent detail will go here.'}</p>
      </div>
    </section>
  )
}
