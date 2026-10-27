import { useEffect, useId, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import type { CheckInQuestion, CheckInResponse } from './checkInTypes'
import { Link } from 'react-router-dom'
import CheckInIcon from './CheckInIcon'

interface Props {
  question: CheckInQuestion
  busy: boolean
  error: boolean
  onRespond: (answer: CheckInResponse) => void
}

export default function QuestionCard({ question, busy, error, onRespond }: Props) {
  const [expanded, setExpanded] = useState(question.response_mode === 'options')
  const [selected, setSelected] = useState('')
  const [comment, setComment] = useState('')
  const [attempt, setAttempt] = useState<CheckInResponse | null>(null)
  const [failedImages, setFailedImages] = useState<string[]>([])
  const errorRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (error) errorRef.current?.scrollIntoView({ block: 'center' })
  }, [error])
  const id = useId()
  const positive = question.positive ?? { value: 'yes', label: question.type === 'STILL_RELEVANT' ? 'Still interested' : 'Yes, that’s right' }
  const negative = question.negative ?? { value: 'no', label: question.type === 'STILL_RELEVANT' ? 'Not anymore' : 'Not quite' }
  const option = question.options.find(item => item.value === selected)
  const respond = (answer: CheckInResponse) => { setAttempt(answer); onRespond(answer) }
  function clarify(event: FormEvent) {
    event.preventDefault()
    if (option && (!option.comment_required || comment.trim())) respond({ response: option.value, comment: option.allows_comment || option.value === 'other' ? comment.trim() || null : null })
  }
  const images = question.supporting_images.slice(0, 3).filter(image => !failedImages.includes(image.url))

  return <article className={`checkin-card${question.response_mode === 'options' ? ' checkin-card--options' : ''}`} aria-labelledby={`${id}-summary`} aria-busy={busy}>
    <div className="checkin-category"><span className="checkin-category-icon"><CheckInIcon name={question.domain} /></span><span>{question.domain}</span></div>
    <h2 id={`${id}-summary`} className="checkin-summary">{question.summary}</h2>
    {images.length > 0 && <div className="checkin-previews">{images.map(image => <img key={image.url} src={image.url} alt={image.alt} width="120" height="148" onError={() => setFailedImages(previous => [...previous, image.url])} />)}</div>}
    <p className="checkin-question">{question.question}</p>
    {question.run_id && <Link className="checkin-trace" to={`/agent-activity?run=${encodeURIComponent(question.run_id)}`}>See why Pingo asked →</Link>}
    {question.response_mode !== 'options' && <div className="checkin-response-actions">
      <button className={`checkin-response checkin-response-no${busy && attempt?.response === negative.value ? ' checkin-selected' : ''}`} disabled={busy} aria-label={negative.label} onClick={() => respond({ response: negative.value, comment: null })}><CheckInIcon name="close" /></button>
      <button className={`checkin-response checkin-response-yes${busy && attempt?.response === positive.value ? ' checkin-selected' : ''}`} disabled={busy} aria-label={positive.label} onClick={() => respond({ response: positive.value, comment: null })}><CheckInIcon name="check" /></button>
    </div>}
    {question.response_mode !== 'options' && <button className="checkin-more" disabled={busy} aria-expanded={expanded} aria-controls={`${id}-clarification`} onClick={() => setExpanded(value => !value)}><CheckInIcon name="message" />{expanded ? 'A little less' : 'Tell me more'}</button>}
    {expanded && <div className="checkin-clarification" id={`${id}-clarification`}>
      <p>{question.context ?? question.question}</p>
      {question.options.length > 0 && <form onSubmit={clarify}>
        <fieldset disabled={busy}><legend>Choose what fits</legend>
          {question.options.map(item => <label className={`checkin-option${selected === item.value ? ' checkin-option-selected' : ''}`} key={item.value}>
            <input type="radio" name={`${id}-option`} value={item.value} checked={selected === item.value} onChange={() => setSelected(item.value)} />{item.label}
          </label>)}
          {(option?.allows_comment || option?.value === 'other') && <label className="checkin-comment">Anything you’d like to add? {!option?.comment_required && <span>(optional)</span>}<textarea value={comment} onChange={event => setComment(event.target.value)} required={option?.comment_required} maxLength={500} rows={3} placeholder="Tell me what you had in mind…" /></label>}
        </fieldset>
        <button className="checkin-primary" type="submit" disabled={busy || !option || (!!option.comment_required && !comment.trim())}>{busy ? 'Saving…' : 'Save answer'}</button>
      </form>}
    </div>}
    {busy && <p className="checkin-saving" role="status">Saving your answer…</p>}
    {error && <div className="checkin-error" ref={errorRef} role="alert"><p>Your answer couldn’t be saved. Please try again.</p><button className="checkin-text-button" disabled={busy} onClick={() => attempt && onRespond(attempt)}>Try again</button></div>}
  </article>
}
