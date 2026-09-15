// 3D-shaded human presenter character that reacts to voice-chat state and
// holds up a prop matching the current weather (umbrella in rain, sun-shade
// card in heat/sun). Layered SVG volumes with gradients for a soft 3D look —
// no external assets or 3D lib needed.
//
// idle:      gentle bob, periodic hello wave (right hand), prop in left hand
// listening: raises mic in right hand, glow rings pulse
// thinking:  right hand to chin, sparkle above head
// speaking:  gestures with right hand + animated mouth
//
// weatherProp: 'umbrella' | 'shade-card' | 'card' | null (no data yet)
// mood:        'improved' (risk dropped → celebrate) |
//              'worsened' (risk rose → look concerned) | null

const STATE_COLOR = {
  idle: '#38bdf8',
  listening: '#22c55e',
  thinking: '#a78bfa',
  speaking: '#f59e0b',
}

export default function VoiceCharacter({ state = 'idle', size = 72, weatherProp = null, mood = null }) {
  const celebrating = mood === 'improved'
  const concerned = mood === 'worsened'
  // A risk reaction overrides the state tint so the change reads instantly.
  const color = celebrating ? '#22c55e' : concerned ? '#f97316' : STATE_COLOR[state] || STATE_COLOR.idle
  const holding = Boolean(weatherProp)

  return (
    <div
      className="relative flex items-center justify-center flex-shrink-0"
      style={{ width: size, height: size }}
    >
      {/* Glow halo — makes the character noticeable at a glance */}
      <span
        className="absolute inset-[-4px] rounded-full transition-all duration-500"
        style={{
          background: `radial-gradient(circle, ${color}33 0%, ${color}11 55%, transparent 70%)`,
          boxShadow: state === 'idle' ? 'none' : `0 0 14px 2px ${color}55`,
        }}
      />
      {/* Pulse rings while listening */}
      {state === 'listening' && (
        <span
          className="absolute inset-[-2px] rounded-full animate-ping"
          style={{ background: `${color}22` }}
        />
      )}

      <svg
        viewBox="0 0 120 120"
        width={size}
        height={size}
        className={celebrating ? 'vc-stage vc-stage-cheer' : concerned ? 'vc-stage vc-stage-worry' : 'vc-stage'}
        style={{ overflow: 'visible' }}
      >
        <style>{`
          .vc-stage { animation: vc-bob 3.2s ease-in-out infinite; }
          @keyframes vc-bob {
            0%, 100% { transform: translateY(0px); }
            50% { transform: translateY(-3px); }
          }
          .vc-stage-cheer { animation: vc-cheer 0.5s ease-in-out infinite; }
          @keyframes vc-cheer {
            0%, 100% { transform: translateY(0px) scale(1); }
            50% { transform: translateY(-6px) scale(1.03); }
          }
          .vc-stage-worry { animation: vc-worry 0.7s ease-in-out infinite; }
          @keyframes vc-worry {
            0%, 100% { transform: translateY(0px); }
            35% { transform: translateY(1px); }
            70% { transform: translateY(0px); }
          }
          .vc-arm-cheer { animation: vc-arm-cheer 0.45s ease-in-out infinite; transform-origin: 92px 74px; }
          @keyframes vc-arm-cheer {
            0%, 100% { transform: rotate(-95deg); }
            50% { transform: rotate(-118deg); }
          }
          .vc-arm-worry { animation: vc-arm-worry 0.9s ease-in-out infinite; transform-origin: 92px 74px; }
          @keyframes vc-arm-worry {
            0%, 100% { transform: rotate(-58deg); }
            50% { transform: rotate(-66deg); }
          }
          .vc-confetti { animation: vc-confetti 1.2s linear infinite; }
          @keyframes vc-confetti {
            0% { transform: translateY(-4px) rotate(0deg); opacity: 0; }
            20% { opacity: 1; }
            100% { transform: translateY(30px) rotate(200deg); opacity: 0; }
          }
          .vc-arm-wave { animation: vc-wave 1.5s ease-in-out infinite; transform-origin: 92px 74px; }
          @keyframes vc-wave {
            0%, 100% { transform: rotate(-14deg); }
            50% { transform: rotate(26deg); }
          }
          .vc-arm-gesture { animation: vc-gesture 1.1s ease-in-out infinite; transform-origin: 92px 74px; }
          @keyframes vc-gesture {
            0%, 100% { transform: rotate(-10deg) translateX(0px); }
            50% { transform: rotate(14deg) translateX(2px); }
          }
          .vc-arm-think { animation: vc-think 2.4s ease-in-out infinite; transform-origin: 92px 74px; }
          @keyframes vc-think {
            0%, 100% { transform: rotate(2deg); }
            50% { transform: rotate(-10deg) translateY(-2px); }
          }
          .vc-arm-listen { animation: vc-listen 1.3s ease-in-out infinite; transform-origin: 92px 74px; }
          @keyframes vc-listen {
            0%, 100% { transform: rotate(6deg); }
            50% { transform: rotate(16deg); }
          }
          .vc-prop { animation: vc-sway 3.2s ease-in-out infinite; transform-origin: 28px 58px; }
          @keyframes vc-sway {
            0%, 100% { transform: rotate(-3deg); }
            50% { transform: rotate(4deg); }
          }
          .vc-head { animation: vc-head 4.5s ease-in-out infinite; transform-origin: 60px 52px; }
          @keyframes vc-head {
            0%, 100% { transform: rotate(0deg); }
            30% { transform: rotate(3deg); }
            65% { transform: rotate(-3deg); }
          }
          .vc-blink { animation: vc-blink 4.2s infinite; transform-origin: 53px 49px; transform-box: view-box; }
          @keyframes vc-blink {
            0%, 93%, 100% { transform: scaleY(1); }
            96% { transform: scaleY(0.08); }
          }
          .vc-sparkle { animation: vc-sparkle 1.8s ease-in-out infinite; }
          @keyframes vc-sparkle {
            0%, 100% { opacity: 0.2; transform: translateY(0px) scale(0.8); }
            50% { opacity: 1; transform: translateY(-4px) scale(1.15); }
          }
          .vc-shadow { animation: vc-shadow 3.2s ease-in-out infinite; }
          @keyframes vc-shadow {
            0%, 100% { transform: scaleX(1); opacity: 0.35; }
            50% { transform: scaleX(0.86); opacity: 0.22; }
          }
        `}</style>

        <defs>
          {/* Skin gradient for arm cylinders */}
          <linearGradient id="vcArmG" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f3c19d" />
            <stop offset="100%" stopColor="#d99a72" />
          </linearGradient>
          {/* Torso shading */}
          <linearGradient id="vcTorso" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2b4d8f" />
            <stop offset="55%" stopColor="#1f3a6e" />
            <stop offset="100%" stopColor="#152a52" />
          </linearGradient>
          {/* Head volume */}
          <radialGradient id="vcHeadG" cx="0.38" cy="0.32" r="0.85">
            <stop offset="0%" stopColor="#ffdcb8" />
            <stop offset="45%" stopColor="#f3b98c" />
            <stop offset="100%" stopColor="#c98a5e" />
          </radialGradient>
          {/* Collar */}
          <radialGradient id="vcCollar" cx="0.5" cy="0.3" r="0.9">
            <stop offset="0%" stopColor="#67e8f9" />
            <stop offset="100%" stopColor="#0ea5e9" />
          </radialGradient>
          {/* Umbrella canopy panels (alternating shades for depth) */}
          <linearGradient id="vcUmbA" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#60a5fa" />
            <stop offset="100%" stopColor="#2563eb" />
          </linearGradient>
          <linearGradient id="vcUmbB" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#93c5fd" />
            <stop offset="100%" stopColor="#3b82f6" />
          </linearGradient>
          {/* Sun-shade card */}
          <linearGradient id="vcCard" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#fef3c7" />
            <stop offset="100%" stopColor="#fcd34d" />
          </linearGradient>
          <radialGradient id="vcSun" cx="0.4" cy="0.35" r="0.8">
            <stop offset="0%" stopColor="#fde68a" />
            <stop offset="100%" stopColor="#f59e0b" />
          </radialGradient>
        </defs>

        {/* Ground shadow (3D depth cue) */}
        <ellipse className="vc-shadow" cx="60" cy="112" rx="26" ry="4.5" fill="#0a1226" />

        {/* ---- WEATHER PROP (left hand) — drawn behind body/head ---- */}
        {holding && (
          <g className="vc-prop">
            {weatherProp === 'umbrella' && (
              <g>
                {/* ferrule tip */}
                <line x1="24" y1="14" x2="24" y2="20" stroke="#1e3a8a" strokeWidth="2" strokeLinecap="round" />
                {/* canopy: three shaded panels + ribs */}
                <path d="M 8 36 Q 10 22 24 20 Q 16 24 16 36 Z" fill="url(#vcUmbA)" />
                <path d="M 16 36 Q 16 24 24 20 L 24 36 Z" fill="url(#vcUmbB)" />
                <path d="M 24 36 L 24 20 Q 32 24 32 36 Z" fill="url(#vcUmbA)" />
                <path d="M 32 36 Q 32 24 40 36 Q 38 22 24 20" fill="url(#vcUmbB)" />
                {/* canopy rim scallops */}
                <path d="M 8 36 Q 12 39 16 36 Q 20 39 24 36 Q 28 39 32 36 Q 36 39 40 36" stroke="#1e3a8a" strokeWidth="1.4" fill="none" strokeLinecap="round" />
                {/* shaft + curved handle into the hand */}
                <path d="M 24 36 L 24 52 Q 24 58 28 58" stroke="#1e3a8a" strokeWidth="2.4" fill="none" strokeLinecap="round" />
                {/* rain drops bouncing off the canopy */}
                <g fill="#7dd3fc">
                  <circle cx="7" cy="44" r="1.4">
                    <animate attributeName="cy" values="42;47;42" dur="1.1s" repeatCount="indefinite" />
                    <animate attributeName="opacity" values="1;0.2;1" dur="1.1s" repeatCount="indefinite" />
                  </circle>
                  <circle cx="43" cy="47" r="1.4">
                    <animate attributeName="cy" values="45;50;45" dur="0.9s" repeatCount="indefinite" />
                    <animate attributeName="opacity" values="0.2;1;0.2" dur="0.9s" repeatCount="indefinite" />
                  </circle>
                </g>
              </g>
            )}
            {(weatherProp === 'shade-card' || weatherProp === 'card') && (
              <g>
                {/* stick from hand up to the card */}
                <line x1="28" y1="58" x2="25" y2="47" stroke="#8a5a3c" strokeWidth="2.2" strokeLinecap="round" />
                {/* card */}
                <rect x="14" y="22" width="22" height="26" rx="4" fill="url(#vcCard)" stroke="#b45309" strokeWidth="1.2" />
                {weatherProp === 'shade-card' ? (
                  /* sun icon with rays */
                  <g>
                    <circle cx="25" cy="32" r="4.6" fill="url(#vcSun)" />
                    <g stroke="#b45309" strokeWidth="1.4" strokeLinecap="round">
                      <line x1="25" y1="24.5" x2="25" y2="26.5" />
                      <line x1="25" y1="37.5" x2="25" y2="39.5" />
                      <line x1="17.5" y1="32" x2="19.5" y2="32" />
                      <line x1="30.5" y1="32" x2="32.5" y2="32" />
                      <line x1="19.7" y1="26.7" x2="21.1" y2="28.1" />
                      <line x1="28.9" y1="35.9" x2="30.3" y2="37.3" />
                      <line x1="30.3" y1="26.7" x2="28.9" y2="28.1" />
                      <line x1="21.1" y1="35.9" x2="19.7" y2="37.3" />
                    </g>
                  </g>
                ) : (
                  /* cloud icon on the plain info card */
                  <g>
                    <ellipse cx="22" cy="34" rx="5" ry="3.4" fill="#e2e8f0" />
                    <ellipse cx="27" cy="32.6" rx="4" ry="3" fill="#f8fafc" />
                    <ellipse cx="29.5" cy="35" rx="4" ry="2.6" fill="#cbd5e1" />
                  </g>
                )}
              </g>
            )}
          </g>
        )}

        {/* ---- RIGHT ARM (gesture limb) — drawn behind body ---- */}
        <g className={
          celebrating ? 'vc-arm-cheer'
          : concerned ? 'vc-arm-worry'
          : state === 'speaking' ? 'vc-arm-gesture'
          : state === 'listening' ? 'vc-arm-listen'
          : state === 'thinking' ? 'vc-arm-think'
          : 'vc-arm-wave'
        }>
          <path d="M 92 74 Q 102 72 101 60" stroke="url(#vcArmG)" strokeWidth="7" fill="none" strokeLinecap="round" />
          {/* Hand pose per state */}
          {state === 'listening' ? (
            <g>
              {/* hand holding a small mic */}
              <circle cx="101" cy="57" r="4.6" fill="url(#vcArmG)" />
              <rect x="98.4" y="47" width="5.4" height="9" rx="2.7" fill="#1e293b" stroke={color} strokeWidth="1.4" />
              <circle cx="101.1" cy="46" r="3.4" fill="#94a3b8" />
              <circle cx="100" cy="45" r="1" fill="#e2e8f0" />
            </g>
          ) : state === 'thinking' ? (
            <g>
              {/* hand cupped under chin */}
              <circle cx="101" cy="57" r="4.6" fill="url(#vcArmG)" />
              <path d="M 96.5 58 Q 101 64 105.5 58" stroke="#f3c19d" strokeWidth="5" fill="none" strokeLinecap="round" />
            </g>
          ) : (
            <g>
              {/* open waving/gesturing hand */}
              <circle cx="101" cy="57" r="4.8" fill="url(#vcArmG)" />
              <g stroke="#f3c19d" strokeWidth="3" strokeLinecap="round">
                <line x1="101" y1="53.5" x2="101" y2="49.5" />
                <line x1="97.6" y1="54.6" x2="95.2" y2="51.2" />
                <line x1="104.4" y1="54.6" x2="106.8" y2="51.2" />
              </g>
            </g>
          )}
        </g>

        {/* ---- BODY: soft 3D torso with gradient shading ---- */}
        {/* torso */}
        <path d="M 42 74 Q 40 106 52 110 L 68 110 Q 80 106 78 74 Z" fill="url(#vcTorso)" />
        {/* shirt highlight (specular sheen) */}
        <path d="M 46 76 Q 45 96 52 106" stroke="#7dd3fc" strokeWidth="2.2" opacity="0.35" fill="none" strokeLinecap="round" />
        {/* collar / lanyard */}
        <path d="M 47 74 Q 60 82 73 74" stroke="url(#vcCollar)" strokeWidth="4" fill="none" />

        {/* ---- LEFT ARM: raised holding the prop, or resting ---- */}
        {holding ? (
          <g>
            <path d="M 43 76 Q 33 72 29 62" stroke="url(#vcArmG)" strokeWidth="7" fill="none" strokeLinecap="round" />
            <circle cx="28" cy="58" r="4.2" fill="url(#vcArmG)" />
          </g>
        ) : (
          <g>
            <path d="M 43 76 Q 34 78 32 86" stroke="url(#vcArmG)" strokeWidth="7" fill="none" strokeLinecap="round" />
            <circle cx="31.5" cy="87.5" r="3.8" fill="url(#vcArmG)" />
          </g>
        )}

        {/* ---- HEAD: 3D-shaded with offset highlight ---- */}
        <g className="vc-head">
          {/* neck */}
          <rect x="56" y="64" width="8" height="8" fill="#d99a72" />
          {/* face volume */}
          <circle cx="60" cy="46" r="17" fill="url(#vcHeadG)" />
          {/* hair cap with sheen */}
          <path d="M 43.5 42 A 17 17 0 0 1 76.5 42 Q 72 32 60 31.5 Q 48 32 43.5 42 Z" fill="#3b2b23" />
          <path d="M 47 37.5 Q 54 33 61 34" stroke="#5a4438" strokeWidth="1.6" fill="none" strokeLinecap="round" opacity="0.8" />
          {/* ears */}
          <circle cx="43.4" cy="47" r="2.6" fill="url(#vcHeadG)" />
          <circle cx="76.6" cy="47" r="2.6" fill="url(#vcHeadG)" />
          {/* eyes with catch-light dots */}
          <g className="vc-blink">
            {state === 'speaking' ? (
              <>
                <path d="M 51 48 Q 53.5 45.5 56 48" stroke="#2b1d15" strokeWidth="2" fill="none" strokeLinecap="round" />
                <path d="M 64 48 Q 66.5 45.5 69 48" stroke="#2b1d15" strokeWidth="2" fill="none" strokeLinecap="round" />
              </>
            ) : (
              <>
                <circle cx="53" cy="48" r="2.2" fill="#2b1d15" />
                <circle cx="67" cy="48" r="2.2" fill="#2b1d15" />
                <circle cx="53.8" cy="47.2" r="0.7" fill="#ffffff" />
                <circle cx="67.8" cy="47.2" r="0.7" fill="#ffffff" />
              </>
            )}
          </g>
          {/* raised brows while listening/thinking */}
          {(state === 'listening' || state === 'thinking') && (
            <g stroke="#3b2b23" strokeWidth="1.6" strokeLinecap="round">
              <path d="M 50.5 43.5 Q 53 42 55.5 43.5" fill="none" />
              <path d="M 64.5 43.5 Q 67 42 69.5 43.5" fill="none" />
            </g>
          )}
          {/* blush + mouth */}
          <circle cx="48.5" cy="53" r="2" fill="#f19a7d" opacity="0.5" />
          <circle cx="71.5" cy="53" r="2" fill="#f19a7d" opacity="0.5" />
          {celebrating ? (
            <path d="M 53 56 Q 60 64 67 56" stroke="#8a5a3c" strokeWidth="3" fill="none" strokeLinecap="round" />
          ) : concerned ? (
            <path d="M 55 59.5 Q 60 54.5 65 59.5" stroke="#8a5a3c" strokeWidth="2.2" fill="none" strokeLinecap="round" />
          ) : state === 'thinking' ? (
            <path d="M 55.5 57.5 Q 60 56 64.5 57.5" stroke="#8a5a3c" strokeWidth="2" fill="none" strokeLinecap="round" />
          ) : (
            <path d="M 55 56.5 Q 60 60.5 65 56.5" stroke="#8a5a3c" strokeWidth="2.2" fill="none" strokeLinecap="round" />
          )}
          {/* worried brows while the risk level has risen */}
          {concerned && (
            <g stroke="#3b2b23" strokeWidth="1.8" strokeLinecap="round">
              <path d="M 50 42 Q 53 43.5 55.5 45.5" fill="none" />
              <path d="M 70 42 Q 67 43.5 64.5 45.5" fill="none" />
            </g>
          )}
          {/* open animated mouth while speaking */}
          {state === 'speaking' && !mood && (
            <ellipse cx="60" cy="57" rx="4.5" ry="3" fill="#7c2d2d">
              <animate attributeName="ry" values="3;1.2;4;2;3" dur="0.55s" repeatCount="indefinite" />
            </ellipse>
          )}
          {/* sparkle above head while thinking */}
          {state === 'thinking' && (
            <g className="vc-sparkle">
              <path d="M 78 26 L 79.6 30 L 83.5 31.5 L 79.6 33 L 78 37 L 76.4 33 L 72.5 31.5 L 76.4 30 Z" fill={color} />
            </g>
          )}
        </g>
      </svg>

      {/* Celebration confetti */}
      {celebrating && (
        <span className="absolute inset-0 pointer-events-none" aria-hidden="true">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <span
              key={i}
              className="absolute w-1 h-1 rounded-sm vc-confetti"
              style={{
                background: ['#38bdf8', '#22c55e', '#f59e0b', '#a78bfa', '#f472b6', '#22d3ee'][i],
                left: `${12 + i * 14}%`,
                top: '4%',
                animationDelay: `${i * 0.16}s`,
              }}
            />
          ))}
        </span>
      )}

      {/* Thinking dots */}
      {state === 'thinking' && (
        <span className="absolute -bottom-1 left-1/2 -translate-x-1/2 flex gap-0.5" aria-hidden="true">
          <span className="w-1 h-1 rounded-full animate-pulse" style={{ background: color }} />
          <span className="w-1 h-1 rounded-full animate-pulse" style={{ background: color, animationDelay: '0.2s' }} />
          <span className="w-1 h-1 rounded-full animate-pulse" style={{ background: color, animationDelay: '0.4s' }} />
        </span>
      )}
    </div>
  )
}
