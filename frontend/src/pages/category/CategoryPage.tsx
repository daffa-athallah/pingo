import { Link, Navigate, useParams } from 'react-router-dom'
import { categories } from '../../data/mockData'
import { useRecallEntities } from '../../data/useRecallEntities'
import RecallIcon from '../home/RecallIcon'
import EntityRow from './EntityRow'

// Owner: Daffa. One reusable page for all three categories.
export default function CategoryPage() {
  const { category } = useParams()
  const data = useRecallEntities()
  const selectedCategory = categories.find((item) => item.id === category)
  if (!selectedCategory) return <Navigate to="/" replace />
  const entities = data.entities.filter((entity) => entity.category === selectedCategory.id)

  return (
    <section className="page category-page">
      <div className="category-toolbar"><Link className="category-back" to="/" aria-label="Back to Home"><RecallIcon name="back" /></Link></div>
      <header className="category-header">
        <span className="category-symbol"><RecallIcon name={selectedCategory.id} /></span>
        <div><h1>{selectedCategory.name}</h1><p>{entities.length} {selectedCategory.itemLabel}</p></div>
      </header>
      {data.status === 'loading' && <p className="home-status">Loading your intentions…</p>}
      {data.status === 'error' && <div className="collection-state" role="alert"><h2>Your collection couldn’t load.</h2><p>Give it another try in a moment.</p><button type="button" onClick={data.retry}>Retry</button></div>}
      {data.status === 'ready' && !entities.length && <div className="collection-state"><h2>A little room for discovery.</h2><p>Nothing saved here yet. Your next find might belong here.</p></div>}
      <div className="category-entities">
        {entities.map((entity) => <EntityRow entity={entity} key={entity.id} />)}
      </div>
    </section>
  )
}
