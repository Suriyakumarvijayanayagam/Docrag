/** The GD&T datum feature symbol - same drawing as public/favicon.svg. */
export function DatumMark({ size = 22 }: { size?: number }) {
  return <svg className="datum-mark" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
    <rect width="32" height="32" rx="7" fill="var(--mark-bg)" />
    <rect x="11" y="4.5" width="10" height="8" rx="1" fill="none" stroke="var(--mark-fg)" strokeWidth="2" />
    <path d="M16 12.5v4.5" stroke="var(--mark-fg)" strokeWidth="2" />
    <path d="M16 16.5 22 24.5H10z" fill="#5b8def" />
    <path d="M6 26h20" stroke="var(--mark-fg)" strokeWidth="2" strokeLinecap="round" />
  </svg>
}
