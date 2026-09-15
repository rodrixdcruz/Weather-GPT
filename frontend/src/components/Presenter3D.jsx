// Real WebGL 3D presenter avatar built with react-three-fiber + three.
// Users can drag to rotate (OrbitControls wired manually — no drei dep);
// it auto-rotates gently when idle and pauses while the user drags.
// Keeps the same contract as the 2D mascot: state poses + weather prop +
// risk-trend mood (celebrate a risk drop, look concerned about a rise),
// and falls back to the 2D SVG version when WebGL is unavailable.
import { Component, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import VoiceCharacter from './VoiceCharacter'

const STATE_COLOR = {
  idle: '#38bdf8',
  listening: '#22c55e',
  thinking: '#a78bfa',
  speaking: '#f59e0b',
}

function webglAvailable() {
  try {
    const c = document.createElement('canvas')
    return Boolean(c.getContext('webgl2') || c.getContext('webgl'))
  } catch {
    return false
  }
}

class GLBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { failed: false }
  }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

// OrbitControls without drei: pause auto-rotation while dragging, resume
// a moment after the user lets go.
function Controls() {
  const { camera, gl } = useThree()
  const ref = useRef(null)
  const resume = useRef(null)
  useEffect(() => {
    const c = new OrbitControls(camera, gl.domElement)
    c.enableZoom = false
    c.enablePan = false
    c.minPolarAngle = Math.PI * 0.22
    c.maxPolarAngle = Math.PI * 0.62
    c.target.set(0, 0.15, 0)
    c.autoRotate = true
    c.autoRotateSpeed = 1.2
    c.addEventListener('start', () => {
      c.autoRotate = false
      clearTimeout(resume.current)
    })
    c.addEventListener('end', () => {
      clearTimeout(resume.current)
      resume.current = setTimeout(() => {
        c.autoRotate = true
      }, 2600)
    })
    ref.current = c
    return () => {
      clearTimeout(resume.current)
      c.dispose()
    }
  }, [camera, gl])
  useFrame(() => {
    if (ref.current) ref.current.update()
  })
  return null
}

// Weather prop held in the raised left hand; counter-rotated each frame so
// it stays upright regardless of the arm pose.
function WeatherProp({ kind, mood }) {
  // Arm raised high when celebrating, lowered when concerned, else mid pose.
  const holdZ = mood === 'improved' ? 1.45 : mood === 'worsened' ? 0.5 : 0.95
  const restZ = mood === 'improved' ? 1.0 : mood === 'worsened' ? 0.15 : 0.3
  const armL = useRef(null)
  const prop = useRef(null)
  const dropRefs = useRef([])
  const drops = useMemo(
    () => [0, 1, 2, 3].map((i) => ({ off: i * 0.24, x: -0.5 + i * 0.32, z: 0.14 - (i % 2) * 0.3 })),
    [],
  )

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    if (prop.current && armL.current) {
      prop.current.rotation.z = -armL.current.rotation.z + Math.sin(t * 1.4) * 0.07
    }
    if (kind === 'umbrella') {
      dropRefs.current.forEach((m, i) => {
        if (!m) return
        const p = (t * 0.85 + drops[i].off) % 1
        m.position.y = 0.95 - p * 1.05
        m.scale.setScalar(0.7 + Math.sin(p * Math.PI) * 0.5)
      })
    }
  })

  if (kind === 'umbrella') {
    return (
      <group>
        <group ref={armL} rotation-z={holdZ}>
          {/* left arm + hand */}
          <mesh position={[0, -0.3, 0]}>
            <capsuleGeometry args={[0.075, 0.48, 4, 8]} />
            <meshStandardMaterial color="#f3c19d" roughness={0.55} />
          </mesh>
          <mesh position={[0, -0.62, 0]}>
            <sphereGeometry args={[0.085, 16, 16]} />
            <meshStandardMaterial color="#f3c19d" roughness={0.55} />
          </mesh>
          {/* prop pivot at the hand */}
          <group ref={prop} position={[0, -0.74, 0]}>
            {/* shaft + curved handle */}
            <mesh position={[0, 0.35, 0]}>
              <cylinderGeometry args={[0.024, 0.024, 0.98, 8]} />
              <meshStandardMaterial color="#1e3a8a" roughness={0.4} />
            </mesh>
            <mesh position={[0, -0.13, 0]}>
              <torusGeometry args={[0.075, 0.02, 8, 16, Math.PI]} />
              <meshStandardMaterial color="#1e3a8a" roughness={0.4} />
            </mesh>
            {/* canopy: faceted low-poly cone reads as umbrella panels */}
            <mesh position={[0, 0.88, 0]}>
              <coneGeometry args={[0.56, 0.4, 10]} />
              <meshStandardMaterial color="#3b82f6" roughness={0.35} flatShading />
            </mesh>
            <mesh position={[0, 1.06, 0]}>
              <sphereGeometry args={[0.035, 8, 8]} />
              <meshStandardMaterial color="#1e3a8a" roughness={0.4} />
            </mesh>
            {/* rain bouncing off the canopy */}
            {drops.map((d, i) => (
              <mesh
                key={i}
                ref={(el) => {
                  dropRefs.current[i] = el
                }}
                position={[d.x, 0.6, d.z]}
              >
                <sphereGeometry args={[0.032, 8, 8]} />
                <meshStandardMaterial color="#7dd3fc" roughness={0.2} transparent opacity={0.9} />
              </mesh>
            ))}
          </group>
        </group>
      </group>
    )
  }

  if (kind === 'shade-card' || kind === 'card') {
    const shade = kind === 'shade-card'
    return (
      <group ref={armL} rotation-z={holdZ}>
        <mesh position={[0, -0.3, 0]}>
          <capsuleGeometry args={[0.075, 0.48, 4, 8]} />
          <meshStandardMaterial color="#f3c19d" roughness={0.55} />
        </mesh>
        <mesh position={[0, -0.62, 0]}>
          <sphereGeometry args={[0.085, 16, 16]} />
          <meshStandardMaterial color="#f3c19d" roughness={0.55} />
        </mesh>
        <group ref={prop} position={[0, -0.74, 0]}>
          {/* stick up to the card */}
          <mesh position={[0, 0.2, 0]}>
            <cylinderGeometry args={[0.018, 0.018, 0.4, 8]} />
            <meshStandardMaterial color="#8a5a3c" roughness={0.6} />
          </mesh>
          {/* the card itself */}
          <mesh position={[0, 0.62, 0]}>
            <boxGeometry args={[0.42, 0.5, 0.035]} />
            <meshStandardMaterial color={shade ? '#fcd34d' : '#e2e8f0'} roughness={0.5} />
          </mesh>
          {shade ? (
            <group>
              {/* sun disc with a soft glow */}
              <mesh position={[0.06, 0.66, 0.03]}>
                <sphereGeometry args={[0.095, 16, 16]} />
                <meshStandardMaterial color="#f59e0b" emissive="#f59e0b" emissiveIntensity={0.7} roughness={0.3} />
              </mesh>
              {[0, 1, 2, 3].map((i) => {
                const a = (i / 4) * Math.PI * 2
                return (
                  <mesh key={i} position={[0.06 + Math.cos(a) * 0.16, 0.66 + Math.sin(a) * 0.16, 0.03]}>
                    <sphereGeometry args={[0.018, 8, 8]} />
                    <meshStandardMaterial color="#b45309" roughness={0.5} />
                  </mesh>
                )
              })}
            </group>
          ) : (
            <group>
              {/* little cloud */}
              <mesh position={[-0.05, 0.6, 0.03]}>
                <sphereGeometry args={[0.07, 12, 12]} />
                <meshStandardMaterial color="#f8fafc" roughness={0.7} />
              </mesh>
              <mesh position={[0.04, 0.64, 0.03]}>
                <sphereGeometry args={[0.058, 12, 12]} />
                <meshStandardMaterial color="#f8fafc" roughness={0.7} />
              </mesh>
              <mesh position={[0.09, 0.58, 0.03]}>
                <sphereGeometry args={[0.05, 12, 12]} />
                <meshStandardMaterial color="#cbd5e1" roughness={0.7} />
              </mesh>
            </group>
          )}
        </group>
      </group>
    )
  }

  // No prop: resting left arm
  return (
    <group ref={armL} rotation-z={restZ}>
      <mesh position={[0, -0.3, 0]}>
        <capsuleGeometry args={[0.075, 0.48, 4, 8]} />
        <meshStandardMaterial color="#f3c19d" roughness={0.55} />
      </mesh>
      <mesh position={[0, -0.62, 0]}>
        <sphereGeometry args={[0.085, 16, 16]} />
        <meshStandardMaterial color="#f3c19d" roughness={0.55} />
      </mesh>
    </group>
  )
}

// Celebration confetti: little spinning paper bits raining around the mascot.
const CONFETTI_COLORS = ['#38bdf8', '#22c55e', '#f59e0b', '#a78bfa', '#f472b6']

function Confetti() {
  const bits = useMemo(
    () =>
      Array.from({ length: 14 }, (_, i) => ({
        x: -1.15 + ((i * 0.41) % 2.3),
        z: -0.5 + ((i * 0.53) % 1.0),
        off: (i * 0.13) % 1,
        speed: 0.55 + (i % 5) * 0.12,
        spin: 2 + (i % 4),
        color: CONFETTI_COLORS[i % CONFETTI_COLORS.length],
      })),
    [],
  )
  const refs = useRef([])

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    refs.current.forEach((m, i) => {
      if (!m) return
      const b = bits[i]
      const p = (t * b.speed + b.off) % 1
      m.position.y = 1.6 - p * 2.8
      m.rotation.x = t * b.spin
      m.rotation.z = t * b.spin * 0.7
      m.scale.setScalar(p > 0.86 ? Math.max(0.02, (1 - p) / 0.14) : 1)
    })
  })

  return (
    <group>
      {bits.map((b, i) => (
        <mesh
          key={i}
          ref={(el) => {
            refs.current[i] = el
          }}
          position={[b.x, 1.3, b.z]}
        >
          <boxGeometry args={[0.075, 0.075, 0.012]} />
          <meshStandardMaterial color={b.color} emissive={b.color} emissiveIntensity={0.3} roughness={0.5} />
        </mesh>
      ))}
    </group>
  )
}

function Character({ state, weatherProp, mood }) {
  const root = useRef(null)
  const head = useRef(null)
  const armR = useRef(null)
  const eyes = useRef(null)
  const mouth = useRef(null)
  const sparkle = useRef(null)
  const celebrating = mood === 'improved'
  const concerned = mood === 'worsened'
  const color = STATE_COLOR[state] || STATE_COLOR.idle
  // A risk reaction overrides the state tint so the change reads instantly.
  const accent = celebrating ? '#22c55e' : concerned ? '#f97316' : color

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()

    // Body: hop while celebrating, slump with a nervous tremble when
    // concerned, otherwise the usual gentle bob.
    if (root.current) {
      if (celebrating) {
        root.current.position.y = Math.abs(Math.sin(t * 6)) * 0.24
        root.current.rotation.x = -0.05
        root.current.rotation.z = Math.sin(t * 6) * 0.045
      } else if (concerned) {
        root.current.position.y = -0.06 + Math.sin(t * 3) * 0.012
        root.current.rotation.x = 0.08
        root.current.rotation.z = Math.sin(t * 12) * 0.012
      } else {
        root.current.position.y = Math.sin(t * 2) * 0.05
        root.current.rotation.x = 0
        root.current.rotation.z = 0
      }
    }

    // Head: chin up and bobbing happily, or a worried shake "no".
    if (head.current) {
      if (celebrating) {
        head.current.rotation.x = -0.14
        head.current.rotation.y = Math.sin(t * 5) * 0.22
        head.current.rotation.z = Math.sin(t * 5) * 0.06
      } else if (concerned) {
        head.current.rotation.x = 0.12
        head.current.rotation.y = 0
        head.current.rotation.z = Math.sin(t * 8) * 0.14
      } else {
        head.current.rotation.x = 0
        head.current.rotation.y = Math.sin(t * 0.7) * 0.16
        head.current.rotation.z = Math.sin(t * 0.5) * 0.04
      }
    }

    // Right arm: both arms up for a cheer, hand hovering at the cheek when
    // worried, otherwise the normal voice-state gestures.
    if (armR.current) {
      const g = armR.current
      if (celebrating) g.rotation.z = -2.95 + Math.sin(t * 8) * 0.22
      else if (concerned) g.rotation.z = -2.2 + Math.sin(t * 15) * 0.06
      else if (state === 'listening') g.rotation.z = -1.7 + Math.sin(t * 5) * 0.08
      else if (state === 'speaking') g.rotation.z = -0.7 + Math.sin(t * 6) * 0.28
      else if (state === 'thinking') g.rotation.z = -2.55 + Math.sin(t * 1.6) * 0.05
      else g.rotation.z = -0.45 + Math.sin(t * 6.5) * 0.38
    }

    if (eyes.current) {
      const p = t % 4.2
      eyes.current.scale.y = p < 0.14 ? 0.12 : 1
    }

    if (mouth.current) {
      const talking = state === 'speaking' && !celebrating && !concerned
      mouth.current.scale.y = talking ? 1 + Math.abs(Math.sin(t * 13)) * 0.9 : 1
    }

    if (sparkle.current) {
      sparkle.current.visible = state === 'thinking' || celebrating
      sparkle.current.rotation.y = t * 2
      sparkle.current.scale.setScalar(0.7 + Math.abs(Math.sin(t * 2.6)) * 0.6)
    }
  })

  return (
    <group>
      {/* celebration confetti rains around the mascot while risk improves */}
      {celebrating && <Confetti />}
      {/* state-colored halo ring behind the character (noticeability) */}
      <mesh position={[0, 0.25, -0.6]}>
        <torusGeometry args={[0.88, 0.02, 8, 48]} />
        <meshBasicMaterial color={accent} transparent opacity={0.5} />
      </mesh>
      {/* ground shadow */}
      <mesh position={[0, -0.82, 0]} rotation-x={-Math.PI / 2} scale={[1, 0.5, 1]}>
        <circleGeometry args={[0.55, 24]} />
        <meshBasicMaterial color="#0a1226" transparent opacity={0.4} />
      </mesh>

      <group ref={root} position={[0, -0.1, 0]}>
        {/* torso (shirt) + collar */}
        <mesh position={[0, -0.12, 0]}>
          <capsuleGeometry args={[0.4, 0.32, 6, 16]} />
          <meshStandardMaterial color="#1f3a6e" roughness={0.65} />
        </mesh>
        <mesh position={[0, 0.3, 0]} rotation-x={Math.PI / 2}>
          <torusGeometry args={[0.3, 0.045, 8, 24]} />
          <meshStandardMaterial color="#0ea5e9" roughness={0.4} />
        </mesh>

        {/* right arm: wave / gesture / mic / chin */}
        <group ref={armR} position={[0.46, 0.22, 0]} rotation-z={-0.45}>
          <mesh position={[0, -0.3, 0]}>
            <capsuleGeometry args={[0.075, 0.48, 4, 8]} />
            <meshStandardMaterial color="#f3c19d" roughness={0.55} />
          </mesh>
          <mesh position={[0, -0.62, 0]}>
            <sphereGeometry args={[0.085, 16, 16]} />
            <meshStandardMaterial color="#f3c19d" roughness={0.55} />
          </mesh>
          {state === 'listening' && (
            <group>
              {/* handheld mic */}
              <mesh position={[0, -0.74, 0]}>
                <cylinderGeometry args={[0.038, 0.045, 0.13, 10]} />
                <meshStandardMaterial color="#1e293b" roughness={0.35} />
              </mesh>
              <mesh position={[0, -0.85, 0]}>
                <sphereGeometry args={[0.07, 12, 12]} />
                <meshStandardMaterial color="#94a3b8" metalness={0.65} roughness={0.25} />
              </mesh>
            </group>
          )}
        </group>

        {/* left arm + weather prop */}
        <group position={[-0.46, 0.22, 0]}>
          <WeatherProp kind={weatherProp} mood={mood} />
        </group>

        {/* head */}
        <group ref={head} position={[0, 0.62, 0]}>
          <mesh position={[0, 0.02, 0]}>
            <cylinderGeometry args={[0.09, 0.1, 0.14, 10]} />
            <meshStandardMaterial color="#d99a72" roughness={0.55} />
          </mesh>
          <mesh position={[0, 0.44, 0]}>
            <sphereGeometry args={[0.42, 28, 28]} />
            <meshStandardMaterial color="#f3b98c" roughness={0.55} />
          </mesh>
          {/* hair cap */}
          <mesh position={[0, 0.45, 0]} rotation-x={-0.12}>
            <sphereGeometry args={[0.435, 24, 16, 0, Math.PI * 2, 0, 1.85]} />
            <meshStandardMaterial color="#3b2b23" roughness={0.75} side={2} />
          </mesh>
          {/* ears */}
          <mesh position={[-0.42, 0.42, 0]}>
            <sphereGeometry args={[0.07, 10, 10]} />
            <meshStandardMaterial color="#f3b98c" roughness={0.55} />
          </mesh>
          <mesh position={[0.42, 0.42, 0]}>
            <sphereGeometry args={[0.07, 10, 10]} />
            <meshStandardMaterial color="#f3b98c" roughness={0.55} />
          </mesh>
          {/* eyes (blink via group scale) */}
          <group ref={eyes} position={[0, 0.47, 0]}>
            <mesh position={[-0.14, 0, 0.375]}>
              <sphereGeometry args={[0.055, 12, 12]} />
              <meshStandardMaterial color="#2b1d15" roughness={0.3} />
            </mesh>
            <mesh position={[0.14, 0, 0.375]}>
              <sphereGeometry args={[0.055, 12, 12]} />
              <meshStandardMaterial color="#2b1d15" roughness={0.3} />
            </mesh>
            <mesh position={[-0.125, 0.02, 0.415]}>
              <sphereGeometry args={[0.016, 8, 8]} />
              <meshBasicMaterial color="#ffffff" />
            </mesh>
            <mesh position={[0.155, 0.02, 0.415]}>
              <sphereGeometry args={[0.016, 8, 8]} />
              <meshBasicMaterial color="#ffffff" />
            </mesh>
          </group>
          {/* blush */}
          <mesh position={[-0.24, 0.32, 0.32]} rotation-y={-0.6}>
            <circleGeometry args={[0.05, 12]} />
            <meshBasicMaterial color="#f19a7d" transparent opacity={0.45} />
          </mesh>
          <mesh position={[0.24, 0.32, 0.32]} rotation-y={0.6}>
            <circleGeometry args={[0.05, 12]} />
            <meshBasicMaterial color="#f19a7d" transparent opacity={0.45} />
          </mesh>
          {/* worried brows while the risk level has risen */}
          {concerned && (
            <group>
              <mesh position={[-0.14, 0.56, 0.37]} rotation-z={0.4}>
                <boxGeometry args={[0.13, 0.026, 0.02]} />
                <meshStandardMaterial color="#3b2b23" roughness={0.7} />
              </mesh>
              <mesh position={[0.14, 0.56, 0.37]} rotation-z={-0.4}>
                <boxGeometry args={[0.13, 0.026, 0.02]} />
                <meshStandardMaterial color="#3b2b23" roughness={0.7} />
              </mesh>
            </group>
          )}
          {/* mouth: beam while celebrating, frown when concerned, animated
              open mouth while speaking, calm smile otherwise */}
          {celebrating ? (
            <mesh position={[0, 0.26, 0.38]} rotation-z={Math.PI}>
              <torusGeometry args={[0.12, 0.028, 8, 24, Math.PI]} />
              <meshStandardMaterial color="#8a5a3c" roughness={0.5} />
            </mesh>
          ) : concerned ? (
            <mesh position={[0, 0.34, 0.38]}>
              <torusGeometry args={[0.085, 0.02, 8, 20, Math.PI]} />
              <meshStandardMaterial color="#8a5a3c" roughness={0.5} />
            </mesh>
          ) : state === 'speaking' ? (
            <mesh ref={mouth} position={[0, 0.27, 0.39]}>
              <sphereGeometry args={[0.055, 12, 12]} />
              <meshStandardMaterial color="#7c2d2d" roughness={0.4} />
            </mesh>
          ) : (
            <mesh position={[0, 0.3, 0.38]} rotation-z={Math.PI}>
              <torusGeometry args={[0.085, 0.018, 8, 20, Math.PI]} />
              <meshStandardMaterial color="#8a5a3c" roughness={0.5} />
            </mesh>
          )}
          {/* thinking sparkle */}
          <mesh ref={sparkle} position={[0.34, 0.98, 0.1]} visible={state === 'thinking'}>
            <octahedronGeometry args={[0.09, 0]} />
            <meshStandardMaterial color={color} emissive={color} emissiveIntensity={1.2} roughness={0.3} />
          </mesh>
        </group>
      </group>
    </group>
  )
}

export default function Presenter3D({ state = 'idle', size = 72, weatherProp = null, hint = null, mood = null }) {
  const [glOK] = useState(webglAvailable)
  const [failed, setFailed] = useState(false)
  const fallback = <VoiceCharacter state={state} size={size} weatherProp={weatherProp} mood={mood} />
  const accent = mood === 'improved' ? '#22c55e' : mood === 'worsened' ? '#f97316' : STATE_COLOR[state] || STATE_COLOR.idle
  if (!glOK || failed) return fallback

  return (
    <div className="relative flex-shrink-0" style={{ width: size, height: size }}>
      <GLBoundary fallback={fallback}>
        <Suspense fallback={fallback}>
          <Canvas
            dpr={[1, 2]}
            gl={{ alpha: true, antialias: true }}
            camera={{ fov: 42, position: [0, 0.6, 3.6] }}
            style={{ background: 'transparent', touchAction: 'none' }}
            onCreated={({ gl }) => {
              gl.domElement.addEventListener('webglcontextlost', () => setFailed(true))
            }}
          >
            <ambientLight intensity={0.75} />
            <directionalLight position={[2.5, 4, 3.5]} intensity={1.3} />
            <pointLight position={[-2, 1, -1.5]} intensity={0.45} />
            <pointLight position={[1.6, 1.3, 2.2]} intensity={mood ? 1.35 : 1.1} color={accent} />
            <Character state={state} weatherProp={weatherProp} mood={mood} />
            <Controls />
          </Canvas>
        </Suspense>
      </GLBoundary>
      {hint && (
        <span className="absolute -bottom-1 left-1/2 -translate-x-1/2 whitespace-nowrap text-[8px] text-slate-300 animate-pulse pointer-events-none">
          {hint}
        </span>
      )}
    </div>
  )
}
