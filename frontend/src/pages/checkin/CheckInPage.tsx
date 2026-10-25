import PageHeader from '../../components/common/PageHeader'
import EmptyState from '../../components/common/EmptyState'

// Owner: Ica. Validation questions and interactions will be built here.
export default function CheckInPage() {
  return (
    <section className="page checkin-page">
      <PageHeader title="Check-in" description="A few things I'd like to understand better." />
      <div className="checkin-card">
        <EmptyState title="Check-in UI will go here." />
      </div>
    </section>
  )
}
