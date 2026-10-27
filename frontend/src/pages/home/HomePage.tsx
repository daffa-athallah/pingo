import SaveScreenshotButton from '../../features/demo/SaveScreenshotButton'
import { Link, useSearchParams } from 'react-router-dom'
import { categories } from '../../data/mockData'
import { useRecallEntities } from '../../data/useRecallEntities'
import RecallIcon from './RecallIcon'
import EntityRow from '../category/EntityRow'
import PingoMark from '../../components/brand/PingoMark'
import { sortCollection } from '../../data/collectionPresentation'

// Owner: Daffa. Category tabs show entities directly, ready to open their details.
export default function HomePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const data = useRecallEntities()
  const selectedCategory = searchParams.get('category')
  const filter = categories.some((category) => category.id === selectedCategory) ? selectedCategory : 'all'
  const sort = searchParams.get('sort') === 'screenshots' ? 'screenshots' : 'recent'
  const visible = sortCollection(data.entities.filter(item => filter === 'all' || item.category === filter), sort)
  function changeParam(key: string, value: string, defaultValue: string) {
    setSearchParams(previous => {
      const next = new URLSearchParams(previous)
      if (value === defaultValue) next.delete(key)
      else next.set(key, value)
      return next
    }, { replace: true })
  }

  return (
    <section className="page home-page">
      <div className="home-sticky">
        <header className="home-header">
          <PingoMark className="home-pingo-mark" title="pingo" />
          <Link className="home-profile" to="/settings/notifications" aria-label="Profile and notification settings"><RecallIcon name="profile" /></Link>
        </header>
        <div className="home-filters" role="group" aria-label="Show intentions by category">
          {[{ id: 'all' as const, name: 'All' }, ...categories].map((category) => (
            <button key={category.id} type="button" aria-pressed={filter === category.id} onClick={() => changeParam('category', category.id, 'all')}><span>{category.name}</span></button>
          ))}
        </div>
      </div>
      <header className="home-intentions-heading">
        <h1>Good things, saved.<svg className="home-hero-ping" viewBox="0 0 24 24" aria-hidden="true"><path d="m7 11 4-7m2 14 7-3" /></svg></h1>
        <p>Worth another look when the moment is right.</p>
      </header>
      <div className="home-sort"><label className="home-sort-control"><span className="checkin-sr-only">Sort saved things</span>
        <select value={sort} onChange={event => changeParam('sort', event.target.value, 'recent')}><option value="recent">Most recent</option><option value="screenshots">Most screenshots</option></select>
        <svg viewBox="0 0 16 16" aria-hidden="true"><path d="m4 6 4 4 4-4" /></svg>
      </label><SaveScreenshotButton /></div>
      <div id="nearby-slot" />
      <div className="home-collection" aria-live="polite" aria-busy={data.status === 'loading'}>
        {data.status === 'loading' && <p className="home-status" role="status">Finding your saved things…</p>}
        {data.status === 'error' && <div className="collection-state" role="alert"><h2>Your collection couldn’t load.</h2><p>Give it another try in a moment.</p><button type="button" onClick={data.retry}>Retry</button></div>}
        {data.status === 'ready' && visible.length === 0 && <div className="collection-state"><h2>A little room for discovery.</h2><p>{filter === 'all' ? 'Save a screenshot to start your collection.' : 'Nothing saved here yet. Your next find might belong here.'}</p>{filter !== 'all' && <button type="button" onClick={() => changeParam('category', 'all', 'all')}>See all saved things</button>}</div>}
        {data.status === 'ready' && visible.map(entity => <EntityRow entity={entity} key={entity.id} />)}
      </div>
      {data.status === 'ready' && data.source === 'mock' && <p className="checkin-demo">Sample collection · illustrative data</p>}
    </section>
  )
}
