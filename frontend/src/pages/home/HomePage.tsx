import { useSearchParams } from 'react-router-dom'
import { categories } from '../../data/mockData'
import { useRecallEntities } from '../../data/useRecallEntities'
import RecallIcon from './RecallIcon'
import EntityRow from '../category/EntityRow'

// Owner: Daffa. Category tabs show entities directly, ready to open their details.
export default function HomePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const data = useRecallEntities()
  const selectedCategory = searchParams.get('category')
  const filter = categories.some((category) => category.id === selectedCategory) ? selectedCategory : 'all'
  const visibleCategories = categories.filter((category) => filter === 'all' || category.id === filter)

  return (
    <section className="page home-page">
      <header className="home-header">
        <h1><span className="home-brand-mark" aria-hidden="true" />Recall</h1>
        <span className="home-profile" aria-hidden="true"><RecallIcon name="profile" /></span>
      </header>
      <div className="home-filters" role="group" aria-label="Show intentions by category">
        {[{ id: 'all' as const, name: 'All' }, ...categories].map((category) => (
          <button key={category.id} type="button" aria-pressed={filter === category.id} onClick={() => setSearchParams(category.id === 'all' ? {} : { category: category.id }, { replace: true })}>{category.name}</button>
        ))}
      </div>
      <div className="home-entities" aria-live="polite">
        {data.status === 'loading' && <p className="home-status">Loading your intentions…</p>}
        {data.status === 'error' && <p className="home-status" role="alert">{data.message} Is the Recall backend running?</p>}
        {visibleCategories.map((category) => {
          const entities = data.entities.filter((entity) => entity.category === category.id)
          return (
            <section className="home-entity-group" key={category.id} aria-labelledby={`home-${category.id}-heading`}>
              <header className="home-entity-heading">
                <h2 id={`home-${category.id}-heading`}>{category.name}</h2>
                <span>{entities.length} {category.itemLabel}</span>
              </header>
              <div className="category-entities">
                {entities.map((entity) => <EntityRow entity={entity} key={entity.id} />)}
              </div>
            </section>
          )
        })}
      </div>

    </section>
  )
}
