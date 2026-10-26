/** Convert a wall time in an IANA zone without assuming the browser's timezone. */
export function wallTime(instant: Date, zone: string): string {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(instant)
  const part = (key: string) => parts.find(p => p.type === key)?.value ?? ''
  return `${part('year')}-${part('month')}-${part('day')}T${part('hour')}:${part('minute')}`
}
export function zonedInstant(value: string, zone: string): string {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) throw new Error('Enter a complete date and time.')
  const target = Date.parse(`${value}:00Z`)
  let guess = target
  for (let i = 0; i < 4; i++) guess += target - Date.parse(`${wallTime(new Date(guess), zone)}:00Z`)
  if (wallTime(new Date(guess), zone) !== value) throw new Error('This time does not exist in the chosen timezone. Choose another time.')
  if ([-3600000, 3600000].some(offset => wallTime(new Date(guess + offset), zone) === value)) throw new Error('This time occurs twice during a daylight saving change. Choose an unambiguous time.')
  return new Date(guess).toISOString()
}
