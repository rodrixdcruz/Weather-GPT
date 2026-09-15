/*
 * Morphing shell — circle preview ↔ expanded rectangle.
 * Pure presentation: all expansion geometry lives in ReactiveMap.
 */
export default function MapContainer({
  expanded,
  fixed,
  showScrim,
  surfaceRef,
  anchor,
  onActivate,
  onKeyDown,
  onTransitionEnd,
  onScrimClick,
  children,
}) {
  return (
    <div className="map-container">
      {showScrim ? (
        <div
          className={`map-scrim ${expanded ? 'is-visible' : ''}${onScrimClick ? ' is-clickable' : ''}`}
          aria-hidden="true"
          onClick={onScrimClick}
        />
      ) : null}
      <div
        ref={surfaceRef}
        className={`map-surface map-surface--${expanded ? 'expanded' : 'circle'}${fixed ? ' is-fixed' : ''}`}
        style={{ transform: `translate(${anchor.x}px, ${anchor.y}px)` }}
        role={expanded ? 'region' : 'button'}
        aria-label={expanded ? 'Weather map, expanded' : 'Expand weather map'}
        aria-expanded={expanded}
        tabIndex={expanded ? -1 : 0}
        onPointerDown={onActivate}
        onKeyDown={onKeyDown}
        onTransitionEnd={onTransitionEnd}
      >
        {children}
      </div>
    </div>
  )
}
