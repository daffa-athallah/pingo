import { Link } from 'react-router-dom'
import PageHeader from '../../components/common/PageHeader'
import { categories, mockEntities } from '../../data/mockData'

// Owner: Daffa. Placeholder structure for the future Homepage design.
export default function HomePage() {
  return (
    <section className="page home-page">
      <PageHeader title="Recall" />
      <h2>Your intentions</h2>
      <div className="home-categories">
        {categories.map((category) => {
          const count = mockEntities.filter((entity) => entity.category === category.id).length
          return (
            <Link className="home-category-card" to={`/category/${category.id}`} key={category.id}>
              <span className="home-category-name">{category.name}</span>
              <span className="home-category-count">{count} saved {count === 1 ? 'intention' : 'intentions'}</span>
              <span className="home-category-arrow" aria-hidden="true">↗</span>
            </Link>
          )
        })}
      </div>
    </section>
  )
}
