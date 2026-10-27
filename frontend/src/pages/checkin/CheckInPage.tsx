import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useCheckIns } from './CheckInProvider'
import { isCheckInDemo } from './checkInService'
import type { CheckInQuestion, CheckInResponse } from './checkInTypes'
import CheckInIcon from './CheckInIcon'
import QuestionCard from './QuestionCard'
import PingoPageHeader from '../../components/layout/PingoPageHeader'

function Flow({ questions: initialQuestions }: { questions: CheckInQuestion[] }) {
  const { responses, submit } = useCheckIns()
  const [questions] = useState(() => initialQuestions.filter(question => !responses[question.id]))
  const [index, setIndex] = useState(0)
  const [skipped, setSkipped] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)
  const [reviewNote, setReviewNote] = useState('')
  const lock = useRef(false)
  const focusTarget = useRef<HTMLHeadingElement>(null)
  const mounted = useRef(true)
  const navigate = useNavigate()
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  useEffect(() => {
    if (index > 0) {
      window.scrollTo(0, 0)
      focusTarget.current?.focus({ preventScroll: true })
    }
  }, [index])
  const question = questions[index]

  async function respond(answer: CheckInResponse) {
    if (lock.current || !question) return
    lock.current = true
    setBusy(true)
    setError(false)
    try {
      const saved = await submit(question.id, answer)
      if (mounted.current) {
        setReviewNote(saved.agent_review?.state === 'RECORDED'
          ? 'Your answer is saved. In the live app the Open Loop Agent now reads it and updates your intention; this offline example makes no model call.'
          : saved.agent_review?.state === 'FAILED_SAFE' || saved.agent_review?.state === 'SKIPPED'
            ? 'Your answer is saved. Pingo couldn’t update your intention right now.' : '')
        setIndex(value => value + 1)
      }
    } catch { if (mounted.current) setError(true) }
    finally {
      lock.current = false
      if (mounted.current) setBusy(false)
    }
  }
  function move(step: number) {
    if (lock.current) return
    setError(false)
    setIndex(value => Math.min(Math.max(value + step, 0), questions.length - 1))
  }
  const touch = useRef<{ x: number; y: number } | null>(null)
  const swipe = {
    onTouchStart: (event: React.TouchEvent) => { const t = event.touches[0]; touch.current = { x: t.clientX, y: t.clientY } },
    onTouchEnd: (event: React.TouchEvent) => {
      const start = touch.current; touch.current = null
      const t = event.changedTouches[0]
      if (!start || (event.target as HTMLElement).closest('textarea, input')) return
      const dx = t.clientX - start.x, dy = t.clientY - start.y
      if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5) move(dx < 0 ? 1 : -1)  // swipe left = next, right = back
    },
  }
  function skip() {
    if (lock.current || !question) return
    setSkipped(previous => [...previous, question.id])
    setError(false)
    if (index === questions.length - 1) navigate('/')
    else setIndex(value => value + 1)
  }

  return <section className="checkin-page">
    <PingoPageHeader action={question && <button className="checkin-text-button" onClick={skip} disabled={busy}>Skip</button>} />
    {reviewNote && <p role="status">{reviewNote}</p>}
    {question ? <>
      <div className="checkin-intro">
        <div className="checkin-progress" role="progressbar" aria-label="Check-in progress" aria-valuenow={index + 1} aria-valuemin={1} aria-valuemax={questions.length} aria-valuetext={`Question ${index + 1} of ${questions.length}`}>
          <span aria-hidden="true">{index + 1} of {questions.length}</span>
          <div className="checkin-progress-bars" aria-hidden="true">{questions.map((item, step) => <span key={item.id} className={`${step <= index ? 'checkin-progress-current' : ''}${skipped.includes(item.id) ? ' checkin-progress-skipped' : ''}`} />)}</div>
        </div>
        <h1 ref={focusTarget} tabIndex={-1}>Check-in</h1>
        <p>A few questions to help me understand you better.</p>
      </div>
      <div {...swipe}>
        <QuestionCard key={question.id} question={question} onRespond={respond} busy={busy} error={error} />
        {questions.length > 1 && <nav className="checkin-pager" aria-label="Move between questions">
          <button onClick={() => move(-1)} disabled={busy || index === 0}>← Back</button>
          <span>Swipe or tap</span>
          <button onClick={() => move(1)} disabled={busy || index === questions.length - 1}>Next →</button>
        </nav>}
      </div>
      <p className="checkin-sr-only" role="status">Question {index + 1} of {questions.length}. {question.summary}</p>
    </> : <div className="checkin-result">
      <span className="checkin-result-icon"><CheckInIcon name={questions.length ? 'check' : 'message'} /></span>
      <h1 ref={focusTarget} tabIndex={-1}>{questions.length ? skipped.length ? 'You’re done for now.' : 'All caught up.' : 'Nothing to check in on.'}</h1>
      <p>{questions.length ? 'Thanks for helping pingo understand you better.' : "pingo doesn't need anything from you right now."}</p>
      {(!questions.length || skipped.length > 0) && <p className="checkin-result-detail">{skipped.length ? 'Anything you skipped will be here when you’re ready.' : "We'll ask when there's something worth clarifying."}</p>}
      <Link to="/" className="checkin-primary">Back to Home</Link>
    </div>}
    {isCheckInDemo && <p className="checkin-demo">Sample mode · Answers stay in this browser</p>}
  </section>
}

export default function CheckInPage() {
  const { questions, loading, loadError, reload } = useCheckIns()
  useEffect(() => { reload() }, [reload])
  if (loading || loadError) return <section className="checkin-page"><PingoPageHeader /><div className="checkin-result">
    <h1>Check-in</h1>
    {loading ? <p role="status">Finding a few things to check in on…</p> : <div className="checkin-load-error" role="alert"><p>We couldn’t load your questions.</p><p>Please try again in a moment.</p><button className="checkin-primary" onClick={reload}>Try again</button><Link className="checkin-text-button" to="/">Back to Home</Link></div>}
  </div></section>
  return <Flow questions={questions} />
}
