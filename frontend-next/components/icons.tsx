/**
 * One stroke-drawn icon set, sized and weighted consistently so the interface
 * reads as one family. 20px grid, 1.6 stroke, round joins - anything heavier
 * competes with the text beside it.
 */
type IconProps = { size?: number; className?: string };

function Svg({ size = 16, className, children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      {children}
    </svg>
  );
}

export const IconHome = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 8.4 10 3l7 5.4V16a1 1 0 0 1-1 1h-3.6v-4.8H7.6V17H4a1 1 0 0 1-1-1Z" />
  </Svg>
);

export const IconChat = (p: IconProps) => (
  <Svg {...p}>
    <path d="M17 12.2a2 2 0 0 1-2 2H8.4L4.6 17v-2.8H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2Z" />
    <path d="M7 7.5h6M7 10.2h4" />
  </Svg>
);

export const IconLibrary = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5.5 3h5.7L15 6.8V16a1 1 0 0 1-1 1H5.5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" />
    <path d="M11 3v4h4M7 11h5M7 13.6h3.2" />
  </Svg>
);

export const IconMemory = (p: IconProps) => (
  <Svg {...p}>
    <path d="M10 3.2a2.6 2.6 0 0 0-2.6 2.6v.3a2.4 2.4 0 0 0 0 4.6v.5a2.6 2.6 0 0 0 5.2 0v-.5a2.4 2.4 0 0 0 0-4.6v-.3A2.6 2.6 0 0 0 10 3.2Z" />
    <path d="M10 3.2v13.6" />
  </Svg>
);

export const IconPlus = (p: IconProps) => (
  <Svg {...p}>
    <path d="M10 4.5v11M4.5 10h11" />
  </Svg>
);

export const IconPanel = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3" y="4" width="14" height="12" rx="1.8" />
    <path d="M8 4v12" />
  </Svg>
);

export const IconSun = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="10" cy="10" r="3.2" />
    <path d="M10 2.6v1.6M10 15.8v1.6M17.4 10h-1.6M4.2 10H2.6M15.2 4.8l-1.1 1.1M5.9 14.1l-1.1 1.1M15.2 15.2l-1.1-1.1M5.9 5.9 4.8 4.8" />
  </Svg>
);

export const IconMoon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M16 11.8A6.4 6.4 0 0 1 8.2 4a6.4 6.4 0 1 0 7.8 7.8Z" />
  </Svg>
);

export const IconAuto = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="10" cy="10" r="6.6" />
    <path d="M10 3.4v13.2a6.6 6.6 0 0 0 0-13.2Z" fill="currentColor" stroke="none" />
  </Svg>
);

export const IconUpload = (p: IconProps) => (
  <Svg {...p}>
    <path d="M10 13.4V4.2M6.6 7.6 10 4.2l3.4 3.4" />
    <path d="M4 13v2a1.6 1.6 0 0 0 1.6 1.6h8.8A1.6 1.6 0 0 0 16 15v-2" />
  </Svg>
);

export const IconTrash = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4.6 5.8h10.8M8.2 5.8V4.4a1 1 0 0 1 1-1h1.6a1 1 0 0 1 1 1v1.4" />
    <path d="M6 5.8 6.6 16a1 1 0 0 0 1 .9h4.8a1 1 0 0 0 1-.9L14 5.8" />
  </Svg>
);

export const IconShield = (p: IconProps) => (
  <Svg {...p}>
    <path d="M10 3.2 4.8 5.3v4.2c0 3.2 2.1 6.1 5.2 7.3 3.1-1.2 5.2-4.1 5.2-7.3V5.3Z" />
    <path d="m7.9 10 1.6 1.6 3-3.2" />
  </Svg>
);

export const IconArrow = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 10h11M11 6l4 4-4 4" />
  </Svg>
);

export const IconSearchDoc = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5.5 3h5.2L14.5 6.8V9" />
    <path d="M10.7 3v3.8h3.8" />
    <path d="M14.5 16.6H5.5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1" />
    <circle cx="12.4" cy="12.4" r="2.6" />
    <path d="m14.4 14.4 1.9 1.9" />
  </Svg>
);

/** Empty state: a page with nothing on it yet. Decorative only. */
export const ArtEmptyLibrary = ({ className }: { className?: string }) => (
  <svg
    width="96"
    height="72"
    viewBox="0 0 96 72"
    fill="none"
    className={className}
    aria-hidden
  >
    <rect x="26" y="8" width="44" height="56" rx="4" className="fill-panel-2 stroke-rule-2" strokeWidth="1.5" />
    <path d="M36 24h24M36 32h24M36 40h16" className="stroke-rule-2" strokeWidth="1.5" strokeLinecap="round" />
    <circle cx="70" cy="52" r="12" className="fill-panel stroke-accent" strokeWidth="1.5" />
    <path d="M70 47v10M65 52h10" className="stroke-accent" strokeWidth="1.6" strokeLinecap="round" />
  </svg>
);
