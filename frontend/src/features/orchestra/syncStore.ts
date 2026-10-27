import { useSyncExternalStore } from 'react'
import { getRunRecord, startUpload } from '../../services/runsApi'
import type { RunRecord } from '../../services/runsApi'

/** Screenshots chosen on Home, processed one at a time (the store has a single writer). Lives outside React so the Agent Activity page can follow the run. */
export interface SyncState { busy: boolean; index: number; total: number; runId: string | null; done: RunRecord[]; error: string | null }
let state: SyncState = { busy: false, index: 0, total: 0, runId: null, done: [], error: null }
const listeners = new Set<() => void>()
const set = (next: Partial<SyncState>) => { state = { ...state, ...next }; listeners.forEach((fn) => fn()) }
const subscribe = (fn: () => void) => { listeners.add(fn); return () => { listeners.delete(fn) } }
export const useSync = () => useSyncExternalStore(subscribe, () => state)

async function waitFor(runId: string): Promise<RunRecord> {
  const deadline = Date.now() + 15 * 60_000
  while (Date.now() < deadline) {
    try {
      const run = await getRunRecord(runId)
      if (run.status !== 'running') return run
    } catch { /* the server is busy; ask again */ }
    await new Promise((resolve) => window.setTimeout(resolve, 1500))
  }
  throw new Error('Still working after 15 minutes. Check back later; the screenshot may have been saved.')
}

export async function startSync(files: File[]): Promise<void> {
  if (state.busy || !files.length) return
  set({ busy: true, index: 0, total: files.length, runId: null, done: [], error: null })
  try {
    for (const [i, file] of files.entries()) {
      set({ index: i + 1 })
      const started = await startUpload(file)
      set({ runId: started.run_id })
      const run = started.status === 'running' ? await waitFor(started.run_id) : await getRunRecord(started.run_id)
      set({ done: [...state.done, run] })
    }
  } catch (e) { set({ error: e instanceof Error ? e.message : 'Sync failed.' }) } finally { set({ busy: false }) }
}
