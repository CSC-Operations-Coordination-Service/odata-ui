/**
 * Ambient backdrop: an isometric lattice, a few floating cubes, orbital rings and a
 * starfield. Purely decorative — fixed behind the app, never interactive, and hidden
 * from assistive tech. All motion is disabled under prefers-reduced-motion (see
 * globals.css).
 */

// Isometric geometry: a 30° projection, so the vertical rise over a half-width w is
// w * tan(30°) ≈ w * 0.5774. Keeping one constant here keeps every shape on-grid.
const ISO = 0.5774;

function IsoCube({
  x,
  y,
  w,
  depth,
  className = "",
}: {
  x: number;
  y: number;
  w: number;
  depth: number;
  className?: string;
}) {
  const h = w * ISO;
  // Top rhombus, then the two visible side faces hanging off its lower edges.
  const top = `M0,0 L${w},${h} L0,${2 * h} L${-w},${h} Z`;
  const left = `M${-w},${h} L0,${2 * h} L0,${2 * h + depth} L${-w},${h + depth} Z`;
  const right = `M${w},${h} L0,${2 * h} L0,${2 * h + depth} L${w},${h + depth} Z`;

  return (
    <g transform={`translate(${x} ${y})`} className={className}>
      <path d={left} className="iso-face-left" />
      <path d={right} className="iso-face-right" />
      <path d={top} className="iso-face-top" />
      <path d={top} className="iso-edge" fill="none" />
    </g>
  );
}

// Deterministic pseudo-random field: a literal list, so the server and client render
// identical markup (Math.random here would cause a hydration mismatch).
const STARS: [number, number, number, number][] = [
  // x%, y%, radius, animation-delay seconds
  [4, 12, 1.1, 0], [11, 34, 0.7, 1.4], [17, 8, 0.9, 2.9], [23, 61, 1.3, 0.6],
  [29, 24, 0.6, 3.7], [34, 78, 1.0, 1.9], [41, 15, 0.8, 4.4], [47, 46, 1.2, 0.3],
  [52, 88, 0.7, 2.2], [58, 29, 1.0, 3.1], [63, 68, 0.9, 1.1], [69, 6, 1.2, 4.9],
  [74, 52, 0.7, 2.6], [79, 83, 1.1, 0.9], [84, 19, 0.8, 3.4], [88, 63, 1.0, 1.6],
  [92, 37, 1.3, 4.1], [96, 74, 0.7, 2.4], [8, 71, 0.9, 3.9], [37, 41, 0.7, 0.5],
  [66, 91, 0.8, 2.0], [14, 92, 1.0, 4.6], [55, 5, 0.9, 1.3], [99, 17, 0.8, 3.2],
];

export function SpaceBackdrop() {
  return (
    <div className="space-backdrop" aria-hidden="true">
      <svg
        className="space-backdrop-svg"
        xmlns="http://www.w3.org/2000/svg"
        preserveAspectRatio="xMidYMid slice"
        viewBox="0 0 1600 1000"
      >
        <defs>
          {/* The isometric floor: one rhombus per tile, tiled edge to edge. */}
          <pattern
            id="iso-lattice"
            width="72"
            height={72 * ISO * 2}
            patternUnits="userSpaceOnUse"
          >
            <path
              d={`M0,${72 * ISO} L36,0 L72,${72 * ISO} L36,${72 * ISO * 2} Z`}
              fill="none"
              stroke="var(--lattice)"
              strokeWidth="1"
            />
          </pattern>

          <radialGradient id="nebula-a" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.20" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="nebula-b" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="var(--nebula-2)" stopOpacity="0.16" />
            <stop offset="100%" stopColor="var(--nebula-2)" stopOpacity="0" />
          </radialGradient>

          {/* Fades the lattice out towards the centre so it never fights the content. */}
          <radialGradient id="lattice-fade" cx="50%" cy="45%" r="62%">
            <stop offset="0%" stopColor="#fff" stopOpacity="0.1" />
            <stop offset="45%" stopColor="#fff" stopOpacity="0.45" />
            <stop offset="100%" stopColor="#fff" stopOpacity="1" />
          </radialGradient>
          <mask id="lattice-mask">
            <rect width="1600" height="1000" fill="url(#lattice-fade)" />
          </mask>
        </defs>

        <g className="nebula">
          <ellipse cx="180" cy="140" rx="620" ry="440" fill="url(#nebula-a)" />
          <ellipse cx="1480" cy="880" rx="680" ry="480" fill="url(#nebula-b)" />
        </g>

        <rect
          width="1600"
          height="1000"
          fill="url(#iso-lattice)"
          mask="url(#lattice-mask)"
        />

        {/* Orbital rings, flattened to sit on the same isometric plane. */}
        <g className="orbits">
          <ellipse className="orbit orbit-slow" cx="1330" cy="215" rx="250" ry="144" />
          <ellipse className="orbit orbit-slower" cx="1330" cy="215" rx="380" ry="219" />
          <ellipse className="orbit orbit-slow" cx="215" cy="835" rx="300" ry="173" />
        </g>

        <g className="stars">
          {STARS.map(([x, y, r, delay], index) => (
            <circle
              key={index}
              cx={(x / 100) * 1600}
              cy={(y / 100) * 1000}
              r={r}
              className="star"
              style={{ animationDelay: `${delay}s` }}
            />
          ))}
        </g>

        <g className="cubes">
          <g className="drift drift-a">
            <IsoCube x={130} y={690} w={58} depth={66} />
          </g>
          <g className="drift drift-b">
            <IsoCube x={1470} y={575} w={46} depth={52} />
          </g>
          <g className="drift drift-c">
            <IsoCube x={1300} y={92} w={30} depth={34} />
          </g>
          <g className="drift drift-b">
            <IsoCube x={430} y={905} w={34} depth={39} />
          </g>
          <g className="drift drift-c">
            <IsoCube x={905} y={945} w={24} depth={28} />
          </g>
          <g className="drift drift-a">
            <IsoCube x={62} y={210} w={26} depth={30} />
          </g>
        </g>
      </svg>
    </div>
  );
}
