import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type { CheckInQuestion, CheckInResponse, CheckInSubmission } from './checkInTypes'
import { getCheckIns, respondToCheckIn } from './checkInService'

interface CheckInState {
  questions: CheckInQuestion[]
  responses: Record<string, CheckInResponse>
  loading: boolean
  loadError: boolean
  pendingCount: number
  reload: () => void
  submit: (id: string, answer: CheckInResponse) => Promise<CheckInSubmission>
}
const Context = createContext<CheckInState | null>(null)

export function CheckInProvider({ children }: { children: ReactNode }) {
  const [questions, setQuestions] = useState<CheckInQuestion[]>([])
  const [responses, setResponses] = useState<Record<string, CheckInResponse>>({})
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [revision, setRevision] = useState(0)
  const inFlight = useRef(new Set<string>())
  const reload = useCallback(() => setRevision(value => value + 1), [])
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setLoadError(false)
    getCheckIns(controller.signal).then(data => {
      if (!controller.signal.aborted) setQuestions(data)
    }).catch(() => {
      if (!controller.signal.aborted) setLoadError(true)
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false)
    })
    return () => controller.abort()
  }, [revision])

  useEffect(() => {
    const refresh = () => setRevision(value => value + 1)
    window.addEventListener('recall:data-changed', refresh)
    return () => window.removeEventListener('recall:data-changed', refresh)
  }, [])

  const submit = useCallback(async (id: string, answer: CheckInResponse) => {
    if (inFlight.current.has(id)) throw new Error('Response already saving')
    inFlight.current.add(id)
    try {
      const result = await respondToCheckIn(id, answer)
      setResponses(previous => ({ ...previous, [id]: answer }))
      return result
    } finally { inFlight.current.delete(id) }
  }, [])

  return <Context.Provider value={{ questions, responses, loading, loadError,
    pendingCount: questions.filter(question => !responses[question.id]).length,
    reload, submit,
  }}>{children}</Context.Provider>
}

export function useCheckIns() {
  const context = useContext(Context)
  if (!context) throw new Error('Check-in provider is missing')
  return context
}
