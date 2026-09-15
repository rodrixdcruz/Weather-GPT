export default function MapControls({
  expanded,
  zoom,
  onExpand,
  onCollapse,
  onZoomIn,
  onZoomOut,
  onZoomReset,
}) {
  if (!expanded) {
    return (
      <div className="map-controls">
        <button type="button" className="map-expand-chip" onClick={onExpand} aria-label="Expand weather map">
          <span aria-hidden="true">⤢</span> Expand map
        </button>
      </div>
    )
  }

  return (
    <div className="map-toolbar" role="group" aria-label="Map controls">
      <button type="button" className="map-control-button" onClick={onZoomReset} aria-label="Reset map zoom" disabled={zoom === 1}>⌂</button>
      <button type="button" className="map-control-button" onClick={onZoomOut} aria-label="Zoom out weather map" disabled={zoom <= 1}>−</button>
      <button type="button" className="map-control-button" onClick={onZoomIn} aria-label="Zoom in weather map" disabled={zoom >= 1.75}>+</button>
      <button type="button" className="map-control-button map-control-button--collapse" onClick={onCollapse} aria-label="Collapse weather map">✕ Collapse</button>
    </div>
  )
}
