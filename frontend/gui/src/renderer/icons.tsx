import React from "react";

export interface IconProps {
  size?: number;
  className?: string;
}

function makeIcon(paths: React.ReactNode): React.FC<IconProps> {
  return function Icon({ size = 16, className }: IconProps): React.JSX.Element {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        className={className}
        aria-hidden="true"
      >
        {paths}
      </svg>
    );
  };
}

export const SparkleIcon = makeIcon(<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />);
export const ChatIcon = makeIcon(<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />);
export const PlayIcon = makeIcon(<polygon points="6 3 20 12 6 21 6 3" />);
export const ShieldIcon = makeIcon(<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />);
export const ZapIcon = makeIcon(<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />);
export const ArchiveIcon = makeIcon(
  <React.Fragment>
    <path d="M21 8v13H3V8" />
    <path d="M1 3h22v5H1z" />
    <path d="M10 12h4" />
  </React.Fragment>,
);
export const DatabaseIcon = makeIcon(
  <React.Fragment>
    <ellipse cx="12" cy="5" rx="9" ry="3" />
    <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
    <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
  </React.Fragment>,
);
export const RefreshIcon = makeIcon(
  <React.Fragment>
    <path d="M23 4v6h-6" />
    <path d="M1 20v-6h6" />
    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
  </React.Fragment>,
);
export const MicIcon = makeIcon(
  <React.Fragment>
    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
    <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
    <line x1="12" y1="19" x2="12" y2="23" />
    <line x1="8" y1="23" x2="16" y2="23" />
  </React.Fragment>,
);
export const SendIcon = makeIcon(
  <React.Fragment>
    <line x1="22" y1="2" x2="11" y2="13" />
    <polygon points="22 2 15 22 11 13 2 9 22 2" />
  </React.Fragment>,
);
export const CpuIcon = makeIcon(
  <React.Fragment>
    <rect x="4" y="4" width="16" height="16" rx="2" />
    <rect x="9" y="9" width="6" height="6" />
    <path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3" />
  </React.Fragment>,
);
export const TerminalIcon = makeIcon(
  <React.Fragment>
    <polyline points="4 17 10 11 4 5" />
    <line x1="12" y1="19" x2="20" y2="19" />
  </React.Fragment>,
);
export const CheckIcon = makeIcon(<polyline points="20 6 9 17 4 12" />);