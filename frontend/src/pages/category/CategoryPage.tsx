import { Link, Navigate, useParams } from 'react-router-dom'
import PageHeader from '../../components/common/PageHeader'
import { categories, mockEntities } from '../../data/mockData'

// Owner: Daffa. One reusable page for all three categories.
export default function CategoryPage() {
  const { category } = useParams()
  const selectedCategory = categories.find((item) => item.id === category)

  if (!selectedCategory) return <Navigate to="/" replace />

  const entities = mockEntities.filter((entity) => entity.category === selectedCategory.id)

  return (
    <section className="page category-page">
      <Link className="back-link" to="/">← Home</Link>
      <PageHeader title={selectedCategory.name} description="Category content will go here." />
      <div className="category-entities">
        {entities.map((entity) => (
          <Link className="entity-card" to={`/entity/${entity.id}`} key={entity.id}>
            <h2>{entity.name}</h2>
            <p>{entity.location ? `${entity.location} · ` : ''}{entity.screenshotCount} screenshots</p>
          </Link>
        ))}
      </div>
    </section>
  )
}
