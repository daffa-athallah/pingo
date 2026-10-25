import { Link } from 'react-router-dom'
import type { RecallEntity } from '../../types/recall'
import RecallIcon from '../home/RecallIcon'

// Shared within Daffa's pages so Home tabs and category links stay consistent.
export default function EntityRow({ entity }: { entity: RecallEntity }) {
  return (
    <Link className="entity-card" to={`/entity/${entity.id}`}>
      <img className="entity-card-image" src={entity.imageUrl} alt="" />
      <div className="entity-card-copy">
        <h2>{entity.name}</h2>
        {entity.location && <p>{entity.location}</p>}
        <span className="entity-card-evidence">
          <RecallIcon name="evidence" />
          {entity.screenshotCount} {entity.screenshotCount === 1 ? 'screenshot' : 'screenshots'}
        </span>
      </div>
      <RecallIcon name="chevron" className="entity-card-chevron" />
    </Link>
  )
}
