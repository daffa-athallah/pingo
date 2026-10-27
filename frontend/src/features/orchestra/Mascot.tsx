import type { AgentId } from './orchestraModel'

export type MascotState = 'idle' | 'active' | 'done' | 'rest' | 'quiet'
const EYES = (c = '#2a2540') => <>
  <ellipse cx="46" cy="60" rx="6" ry="7.2" fill={c} /><ellipse cx="74" cy="60" rx="6" ry="7.2" fill={c} />
  <circle cx="48.2" cy="57" r="2.4" fill="#fff" /><circle cx="76.2" cy="57" r="2.4" fill="#fff" />
  <circle cx="44.6" cy="62.6" r="1.1" fill="#fff" opacity=".8" /><circle cx="72.6" cy="62.6" r="1.1" fill="#fff" opacity=".8" />
  <ellipse cx="35" cy="70" rx="6" ry="3.6" fill="#FF8FA8" opacity=".6" /><ellipse cx="85" cy="70" rx="6" ry="3.6" fill="#FF8FA8" opacity=".6" />
  <path d="M54 71 Q60 77 66 71" stroke={c} strokeWidth="2.2" fill="none" strokeLinecap="round" />
</>
const FEET = (c: string) => <><ellipse cx="44" cy="99" rx="11" ry="6.5" fill={c} /><ellipse cx="76" cy="99" rx="11" ry="6.5" fill={c} /></>

/** Four small Pingo workers: one friendly shape, a colour and a tiny prop each. Hand-drawn vector illustrations, no photos or generated art. */
function Evidence() {
  return <>
    <defs><linearGradient id="g-ev" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#7FB4FF" /><stop offset="1" stopColor="#4A86F0" /></linearGradient></defs>
    {FEET('#3C6FD0')}
    <circle cx="30" cy="34" r="12" fill="#5B9BFF" /><circle cx="90" cy="34" r="12" fill="#5B9BFF" />
    <circle cx="30" cy="35" r="6.5" fill="#A9CBFF" /><circle cx="90" cy="35" r="6.5" fill="#A9CBFF" />
    <ellipse cx="60" cy="64" rx="42" ry="37" fill="url(#g-ev)" />
    <ellipse cx="60" cy="78" rx="23" ry="17" fill="#DCEBFF" />
    {EYES()}
    <g className="m-prop"><line x1="93" y1="88" x2="106" y2="102" stroke="#B9783A" strokeWidth="6" strokeLinecap="round" />
      <circle cx="88" cy="78" r="14" fill="rgb(255 255 255 / 45%)" stroke="#E0A93E" strokeWidth="4.5" /><path d="M80 73 Q84 69 90 70" stroke="#fff" strokeWidth="2.4" fill="none" strokeLinecap="round" /></g>
  </>
}
function OpenLoop() {
  return <>
    <defs><linearGradient id="g-ol" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#FFA05A" /><stop offset="1" stopColor="#F4742B" /></linearGradient></defs>
    <path d="M96 84 Q122 78 116 52 Q104 64 92 70 Z" fill="#F4742B" /><path d="M110 58 Q118 54 116 52 Q108 60 104 64 Z" fill="#fff" />
    {FEET('#D95F1E')}
    <path d="M24 46 L30 12 L52 34 Z" fill="#F4742B" /><path d="M96 46 L90 12 L68 34 Z" fill="#F4742B" />
    <path d="M32 40 L34 22 L46 34 Z" fill="#FFC9A3" /><path d="M88 40 L86 22 L74 34 Z" fill="#FFC9A3" />
    <ellipse cx="60" cy="64" rx="42" ry="37" fill="url(#g-ol)" />
    <ellipse cx="38" cy="75" rx="17" ry="11" fill="#fff" /><ellipse cx="82" cy="75" rx="17" ry="11" fill="#fff" /><ellipse cx="60" cy="82" rx="20" ry="14" fill="#fff" />
    {EYES()}<ellipse cx="60" cy="68" rx="3.2" ry="2.4" fill="#2a2540" />
    <g className="m-prop"><rect x="84" y="74" width="30" height="26" rx="3" fill="#FFF6E2" stroke="#C9833F" strokeWidth="2.4" />
      <line x1="99" y1="74" x2="99" y2="100" stroke="#C9833F" strokeWidth="1.6" /><path d="M88 82 H96 M88 88 H96 M88 94 H94 M103 82 H111 M103 88 H111" stroke="#E2B07A" strokeWidth="1.8" strokeLinecap="round" /></g>
  </>
}
function Context() {
  return <>
    <defs><linearGradient id="g-cx" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#7DDB9B" /><stop offset="1" stopColor="#3FAE69" /></linearGradient></defs>
    {FEET('#2E8F52')}
    <path d="M44 32 L50 14 L58 30 Z" fill="#2E8F52" /><path d="M56 28 L62 8 L70 28 Z" fill="#2E8F52" /><path d="M68 30 L76 14 L82 32 Z" fill="#2E8F52" />
    <ellipse cx="60" cy="64" rx="42" ry="37" fill="url(#g-cx)" />
    <ellipse cx="60" cy="78" rx="23" ry="17" fill="#D3F3DD" />
    {EYES()}
    <g className="m-prop"><path d="M82 76 L92 72 L102 77 L112 73 V98 L102 102 L92 97 L82 101 Z" fill="#FFF4D6" stroke="#B88A45" strokeWidth="2.2" strokeLinejoin="round" />
      <path d="M92 72 V97 M102 77 V102" stroke="#D8B87A" strokeWidth="1.6" /><path d="M86 86 Q92 82 97 88 T108 84" stroke="#E5604F" strokeWidth="2" fill="none" strokeLinecap="round" strokeDasharray="1 3.5" /></g>
  </>
}
function Critic() {
  return <>
    <defs><linearGradient id="g-cr" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#CBA3FA" /><stop offset="1" stopColor="#9B6FE0" /></linearGradient></defs>
    {FEET('#7F54C4')}
    <path d="M22 44 L26 12 L50 32 Z" fill="#9B6FE0" /><path d="M98 44 L94 12 L70 32 Z" fill="#9B6FE0" />
    <path d="M29 38 L30 22 L43 32 Z" fill="#FFC1DC" /><path d="M91 38 L90 22 L77 32 Z" fill="#FFC1DC" />
    <ellipse cx="60" cy="64" rx="42" ry="37" fill="url(#g-cr)" />
    <ellipse cx="60" cy="79" rx="22" ry="16" fill="#EBDDFF" />
    {EYES()}
    <g className="m-prop"><line x1="100" y1="72" x2="100" y2="104" stroke="#B9783A" strokeWidth="3.2" strokeLinecap="round" /><line x1="86" y1="76" x2="114" y2="76" stroke="#D9A441" strokeWidth="3" strokeLinecap="round" />
      <path d="M86 76 L80 88 H92 Z M114 76 L108 88 H120 Z" fill="#F2C463" stroke="#D9A441" strokeWidth="1.4" strokeLinejoin="round" /><circle cx="100" cy="74" r="3" fill="#D9A441" /></g>
  </>
}
const ART = { evidence: Evidence, openloop: OpenLoop, context: Context, critic: Critic }
export const NAME_COLOR: Record<AgentId, string> = { evidence: '#4A86F0', openloop: '#F4742B', context: '#3FAE69', critic: '#9B6FE0' }

export default function Mascot({ id, state }: { id: AgentId; state: MascotState }) {
  const Art = ART[id]
  return <svg className={`mascot mascot-${id} is-${state}`} viewBox="0 0 124 110" role="img" aria-label={`${id} agent, ${state}`} style={{ ['--agent' as string]: NAME_COLOR[id] }}>
    <ellipse cx="62" cy="104" rx="44" ry="6" fill="rgb(120 70 30 / 14%)" />
    <g className="m-body"><Art /></g>
  </svg>
}
