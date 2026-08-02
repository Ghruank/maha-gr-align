/* Peacock motifs, drawn inline so nothing is fetched at runtime. */

export function FeatherEye({ size = 42 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      <defs>
        <radialGradient id="pkEye" cx="50%" cy="50%">
          <stop offset="0%" stopColor="#0a2447" />
          <stop offset="38%" stopColor="#123a6b" />
          <stop offset="62%" stopColor="#0d6e6e" />
          <stop offset="100%" stopColor="#1b8a5a" />
        </radialGradient>
      </defs>
      <ellipse cx="32" cy="30" rx="19" ry="23" fill="url(#pkEye)" opacity="0.95" />
      <ellipse cx="32" cy="30" rx="19" ry="23" fill="none" stroke="#c9a227" strokeWidth="1.4" opacity="0.75" />
      <ellipse cx="32" cy="30" rx="11" ry="13.5" fill="#0a2447" opacity="0.85" />
      <ellipse cx="32" cy="29" rx="5" ry="6.5" fill="#c9a227" />
      <path d="M32 53 V62" stroke="#c9a227" strokeWidth="1.6" strokeLinecap="round" opacity="0.8" />
      <g stroke="#e8d48b" strokeWidth="1" opacity="0.55" strokeLinecap="round">
        <path d="M32 7 V2" /><path d="M14 18 L10 14" /><path d="M50 18 L54 14" />
      </g>
    </svg>
  )
}

/** Fanned plume used as decorative page art. */
export function FeatherFan({ width = 190 }: { width?: number }) {
  const plumes = [-34, -17, 0, 17, 34]
  return (
    <svg width={width} height={width * 0.78} viewBox="0 0 200 156" aria-hidden="true">
      <defs>
        <linearGradient id="pkQuill" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%" stopColor="#1b8a5a" stopOpacity="0.25" />
          <stop offset="100%" stopColor="#0d6e6e" stopOpacity="0.8" />
        </linearGradient>
        <radialGradient id="pkEye2" cx="50%" cy="50%">
          <stop offset="0%" stopColor="#0a2447" />
          <stop offset="45%" stopColor="#125f7a" />
          <stop offset="100%" stopColor="#1b8a5a" />
        </radialGradient>
      </defs>
      {plumes.map(a => (
        <g key={a} transform={`rotate(${a} 100 150)`}>
          <path d="M100 150 V44" stroke="url(#pkQuill)" strokeWidth="2.4" strokeLinecap="round" />
          <g opacity="0.28" stroke="#0d6e6e" strokeWidth="1" strokeLinecap="round">
            <path d="M100 120 L88 112" /><path d="M100 120 L112 112" />
            <path d="M100 104 L86 95" /><path d="M100 104 L114 95" />
            <path d="M100 88 L85 79" /><path d="M100 88 L115 79" />
            <path d="M100 72 L86 63" /><path d="M100 72 L114 63" />
          </g>
          <ellipse cx="100" cy="34" rx="13" ry="16" fill="url(#pkEye2)" opacity="0.9" />
          <ellipse cx="100" cy="34" rx="13" ry="16" fill="none" stroke="#c9a227" strokeWidth="1.1" opacity="0.6" />
          <ellipse cx="100" cy="34" rx="7" ry="9" fill="#0a2447" opacity="0.8" />
          <ellipse cx="100" cy="33" rx="3.2" ry="4.2" fill="#c9a227" />
        </g>
      ))}
    </svg>
  )
}
