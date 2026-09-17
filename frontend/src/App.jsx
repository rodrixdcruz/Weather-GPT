import { useEffect, useState } from 'react'
import TopBar from './components/TopBar'
import AlertBanner from './components/AlertBanner'
import WeatherCard from './components/WeatherCard'
import RiskGauge from './components/RiskGauge'
import MapCard from './components/MapCard'
import ChatPanel from './components/ChatPanel'
import SosModal from './components/SosModal'
import LanguageModal from './components/LanguageModal'
import ForecastCard from './components/ForecastCard'
import RiskPanel from './components/RiskPanel'
import SafetyDashboard from './components/SafetyDashboard'
import RoleSelector from './components/RoleSelector'
import LoginPage from './components/LoginPage'
import AdminPanel from './components/AdminPanel'
import { ErrorState, LoadingState, SkeletonCard } from './components/StateViews'
import { SafetyTips, SafeZonesList } from './components/SidePanels'
import { I18N, t } from './i18n'
import { api } from './lib/api'
import { useSession } from './lib/session'
import { getWeatherUIState } from './weather'
import WeatherAtmosphere from './weather/WeatherAtmosphere'
import RiskSafetyPanel from './weather/RiskSafetyPanel'
import ReactiveMap from './weather/map/ReactiveMap'

const FALLBACK_LOCATION = { latitude: 19.076, longitude: 72.8777 } // Mumbai demo default

// Session gate. Nothing in the dashboard mounts until there is a session,
// so no API call can be made without a token — and the role below belongs
// to the session, not to React state the user could fiddle with.
export default function App() {
  const { session, signIn, signOut } = useSession()
  const [language, setLanguage] = useState('en')

  if (!session) {
    return <LoginPage language={language} onLanguageChange={setLanguage} onSignIn={signIn} />
  }

  return (
    <Dashboard
      session={session}
      language={language}
      onLanguageChange={setLanguage}
      onSignOut={signOut}
    />
  )
}

function Dashboard({ session, language, onLanguageChange, onSignOut }) {
  // No scenario picker any more: the weather comes from the location and the
  // live provider, so the app always reads the `normal` path. `scenario` is
  // kept as a constant because the provider contract still takes one, and
  // live providers (open_meteo) ignore it — restoring a selector later is a
  // one-line change.
  const [scenario] = useState('normal')
  const [sosOpen, setSosOpen] = useState(false)
  const [langOpen, setLangOpen] = useState(false)
  const [adminOpen, setAdminOpen] = useState(false)
  const [view, setView] = useState('dashboard') // dashboard | safety

  const [location, setLocation] = useState(FALLBACK_LOCATION)
  const [latInput, setLatInput] = useState(String(FALLBACK_LOCATION.latitude))
  const [lonInput, setLonInput] = useState(String(FALLBACK_LOCATION.longitude))
  const [geoState, setGeoState] = useState('idle') // idle | locating | denied | error

  // The location panel is big by nature (search + coords + actions), so once a
  // location is actually chosen it collapses to a one-line summary. It starts
  // expanded because on a first visit there is nothing chosen yet, and the
  // "change location" button re-opens it afterwards.
  const [locationExpanded, setLocationExpanded] = useState(true)
  const [locationName, setLocationName] = useState(null) // the searched place name, when there is one

  // Place-name search (key-less Open-Meteo geocoding via /geo/search).
  const [searchValue, setSearchValue] = useState('')
  const [searchResults, setSearchResults] = useState(null)
  const [searchBusy, setSearchBusy] = useState(false)
  const [searchError, setSearchError] = useState(null)

  // The role is LOCKED to the session by the backend. There is deliberately
  // no setter: changing role requires logging out (see LoginPage).
  const role = session.role

  const [weather, setWeather] = useState(null)
  const [risk, setRisk] = useState(null)
  const [assessment, setAssessment] = useState(null)
  const [forecast, setForecast] = useState(null)
  const [safeZones, setSafeZones] = useState([])

  const [weatherLoading, setWeatherLoading] = useState(true)
  const [weatherError, setWeatherError] = useState(null)
  const [forecastLoading, setForecastLoading] = useState(true)
  const [forecastError, setForecastError] = useState(null)
  const [riskLoading, setRiskLoading] = useState(true)
  const [riskError, setRiskError] = useState(null)

  // Current weather + safe zones reload with location/scenario.
  useEffect(() => {
    let cancelled = false
    setWeatherLoading(true)
    setWeatherError(null)

    Promise.all([
      api.getCurrentWeather(location.latitude, location.longitude, scenario),
      api.getSafeZones(location.latitude, location.longitude).catch(() => []),
    ])
      .then(([wr, zones]) => {
        if (cancelled) return
        setWeather(wr.weather)
        setRisk(wr.risk)
        setSafeZones(zones)
      })
      .catch((err) => {
        if (!cancelled) setWeatherError(err.message)
      })
      .finally(() => {
        if (!cancelled) setWeatherLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [location, scenario])

  // Forecast reloads with location/scenario.
  useEffect(() => {
    let cancelled = false
    setForecastLoading(true)
    setForecastError(null)
    api
      .getForecast(location.latitude, location.longitude, 5, scenario)
      .then((res) => {
        if (!cancelled) setForecast(res.forecast)
      })
      .catch((err) => {
        if (!cancelled) setForecastError(err.message)
      })
      .finally(() => {
        if (!cancelled) setForecastLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [location, scenario])

  // Risk assessment reloads with location/scenario AND role.
  useEffect(() => {
    let cancelled = false
    setRiskLoading(true)
    setRiskError(null)
    api
      .getRisk(location.latitude, location.longitude, role, scenario)
      .then((res) => {
        if (!cancelled) setAssessment(res)
      })
      .catch((err) => {
        if (!cancelled) setRiskError(err.message)
      })
      .finally(() => {
        if (!cancelled) setRiskLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [location, scenario, role])

  async function searchPlace(event) {
    event.preventDefault()
    const query = searchValue.trim()
    if (!query) return
    setSearchBusy(true)
    setSearchError(null)
    try {
      const res = await api.searchLocations(query, 5)
      setSearchResults(res.results)
    } catch {
      setSearchResults(null)
      setSearchError(t(language, 'searchError'))
    } finally {
      setSearchBusy(false)
    }
  }

  function pickPlace(place) {
    setLatInput(place.latitude.toFixed(4))
    setLonInput(place.longitude.toFixed(4))
    setLocation({ latitude: place.latitude, longitude: place.longitude })
    setLocationName(place.label)
    setSearchResults(null)
    setSearchValue('')
    setLocationExpanded(false)
  }

  function applyLocation() {
    const lat = Number.parseFloat(latInput)
    const lon = Number.parseFloat(lonInput)
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180) {
      setWeatherError(t(language, 'invalidCoords'))
      return
    }
    setGeoState('idle')
    setLocationName(null) // manual coordinates have no place name
    setLocation({ latitude: lat, longitude: lon })
    setLocationExpanded(false)
  }

  function useMyLocation() {
    if (!('geolocation' in navigator)) {
      setGeoState('unsupported')
      return
    }
    setGeoState('locating')
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude } = position.coords
        setLatInput(latitude.toFixed(4))
        setLonInput(longitude.toFixed(4))
        setLocationName(null)
        setLocation({ latitude, longitude })
        setGeoState('idle')
        setLocationExpanded(false)
      },
      () => setGeoState('denied'),
      { timeout: 10000 },
    )
  }

  const overall = assessment
  // Centralized UI state: condition + time-of-day theme + risk interpretation
  // derived from the SAME weather/assessment data the existing cards consume.
  const uiState = getWeatherUIState(weather, assessment)
  const locationBar = locationExpanded ? (
    <section aria-label={t(language, 'locationLabel')} className="bg-gradient-to-b from-navy-900 to-navy-800 border border-border rounded-2xl p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-[11px] uppercase tracking-wide text-slate-300 font-semibold m-0">
          {t(language, 'locationLabel')}
        </h2>
        <button
          type="button"
          onClick={() => setLocationExpanded(false)}
          aria-label={t(language, 'close')}
          title={t(language, 'close')}
          className="text-slate-400 hover:text-slate-100 text-xs px-2 py-0.5 rounded-full border border-border transition"
        >
          ✕
        </button>
      </div>
      <form onSubmit={searchPlace} className="flex flex-col sm:flex-row gap-2 sm:items-center" role="search">
        <div className="flex-1">
          <input
            type="search"
            aria-label={t(language, 'searchPlaceholder')}
            className="w-full bg-navy-700 border border-border rounded-lg px-3 py-2 text-[13px] text-slate-100 outline-none focus:border-sky"
            placeholder={t(language, 'searchPlaceholder')}
            value={searchValue}
            onChange={(e) => setSearchValue(e.target.value)}
          />
        </div>
        <button
          type="submit"
          disabled={searchBusy || !searchValue.trim()}
          className="self-start px-4 py-2 rounded-full text-xs bg-navy-700 border border-border hover:border-sky transition disabled:opacity-50"
        >
          {searchBusy ? t(language, 'searching') : `🔍 ${t(language, 'searchLocations')}`}
        </button>
      </form>
      {searchError && <div role="alert" className="text-[11px] text-yellow-400">{searchError}</div>}
      {searchResults && searchResults.length === 0 && (
        <div className="text-[11px] text-slate-300">{t(language, 'noResults')}</div>
      )}
      {searchResults && searchResults.length > 0 && (
        <ul className="list-none m-0 p-0 flex flex-col gap-1" aria-label={t(language, 'searchLocations')}>
          {searchResults.map((place) => (
            <li key={`${place.latitude},${place.longitude},${place.name}`}>
              <button
                type="button"
                onClick={() => pickPlace(place)}
                className="w-full text-left px-3 py-1.5 rounded-lg text-[12.5px] bg-navy-700/70 border border-border hover:border-sky transition text-slate-100"
              >
                📍 {place.label}
                <span className="text-slate-400 text-[10.5px] ml-2">
                  {place.latitude.toFixed(3)}, {place.longitude.toFixed(3)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-col lg:flex-row gap-3 lg:items-end justify-between">
      <div className="flex flex-col sm:flex-row gap-2 sm:items-end">
        <label className="flex flex-col gap-1 text-[11px] uppercase tracking-wide text-slate-300 font-semibold">
          {t(language, 'latitude')}
          <input
            className="bg-navy-700 border border-border rounded-lg px-3 py-2 text-[13px] text-slate-100 w-36 outline-none focus:border-sky"
            inputMode="decimal"
            value={latInput}
            onChange={(e) => setLatInput(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 text-[11px] uppercase tracking-wide text-slate-300 font-semibold">
          {t(language, 'longitude')}
          <input
            className="bg-navy-700 border border-border rounded-lg px-3 py-2 text-[13px] text-slate-100 w-36 outline-none focus:border-sky"
            inputMode="decimal"
            value={lonInput}
            onChange={(e) => setLonInput(e.target.value)}
          />
        </label>
        <button
          type="button"
          onClick={applyLocation}
          className="self-start sm:self-end px-4 py-2 rounded-full text-xs bg-sky text-navy-950 font-semibold"
        >
          {t(language, 'applyLocation')}
        </button>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        {geoState === 'denied' && <span className="text-[11px] text-yellow-400">{t(language, 'geoDenied')}</span>}
        {geoState === 'unsupported' && <span className="text-[11px] text-yellow-400">{t(language, 'geoUnsupported')}</span>}
        {geoState === 'locating' && <span className="text-[11px] text-slate-300">{t(language, 'geoLocating')}</span>}
        <button
          type="button"
          onClick={useMyLocation}
          className="px-4 py-2 rounded-full text-xs bg-navy-700 border border-border hover:border-sky transition"
        >
          📍 {t(language, 'useMyLocation')}
        </button>
      </div>
      </div>
    </section>
  ) : (
    <section
      aria-label={t(language, 'locationLabel')}
      className="bg-gradient-to-b from-navy-900 to-navy-800 border border-border rounded-2xl px-4 py-2.5 flex items-center justify-between gap-3 flex-wrap"
    >
      <div className="flex items-center gap-2 flex-wrap min-w-0">
        <span aria-hidden="true">📍</span>
        <span className="text-[12.5px] font-semibold text-slate-100 truncate">
          {locationName || `${location.latitude.toFixed(4)}, ${location.longitude.toFixed(4)}`}
        </span>
        {locationName && (
          <span className="text-[11px] text-slate-400">
            {location.latitude.toFixed(4)}, {location.longitude.toFixed(4)}
          </span>
        )}
      </div>
      <button
        type="button"
        onClick={() => setLocationExpanded(true)}
        className="px-3 py-1.5 rounded-full text-xs bg-navy-700 border border-border hover:border-sky transition"
      >
        ✏️ {t(language, 'changeLocation')}
      </button>
    </section>
  )

  return (
    <WeatherAtmosphere state={uiState}>
    <div className="min-h-screen">
      <TopBar
        langLabel={I18N[language].name.split(' ')[0]}
        onLangClick={() => setLangOpen(true)}
        onSosClick={() => setSosOpen(true)}
        language={language}
        weather={weather}
        session={session}
        onLogout={onSignOut}
        onAdminClick={() => setAdminOpen(true)}
      />

      <div className="max-w-[1440px] mx-auto p-5 flex flex-col gap-4">
        {/* Locked: the role belongs to the session until logout. */}
        <RoleSelector role={role} language={language} locked />
        {locationBar}

        {/* Safety-first banner + risk/safety summary (text, never color-only) */}
        {uiState.priority === 'safety-first' && (
          <div className="safety-banner" role="alert">
            SAFETY-FIRST MODE — {uiState.riskTheme.level} risk · {uiState.riskTheme.hazard}. {uiState.riskTheme.action}
          </div>
        )}
        {!weatherLoading && !weatherError && <RiskSafetyPanel risk={uiState.riskTheme} />}

        {/* View switcher: Dashboard | Safety */}
        <div role="tablist" aria-label={t(language, 'viewAs')} className="flex gap-2">
          {[
            { id: 'dashboard', label: '📊 ' + t(language, 'forecast'), },
            { id: 'safety', label: '🛡️ ' + t(language, 'navSafety') },
          ].map((tab) => (
            <button
              key={tab.id}
              role="tab"
              aria-selected={view === tab.id}
              onClick={() => setView(tab.id)}
              className={`px-4 py-2 rounded-full text-xs font-semibold border transition ${
                view === tab.id ? 'bg-sky/20 border-sky text-slate-100' : 'bg-navy-800 border-border text-slate-300 hover:border-sky/60'
              }`
              }
            >
              {tab.label}
            </button>
          ))}
        </div>

        {view === 'safety' ? (
          <SafetyDashboard
            location={location}
            role={role}
            scenario={scenario}
            language={language}
            onUseDashboardLocation={() => setLocation({ ...location })}
          />
        ) : (
          <>
            {weatherError && (
          <div role="alert" className="rounded-xl p-4 border border-red-500/40 bg-red-500/5 text-sm">
            {t(language, 'backendError')}
            {weatherError ? <span className="block text-slate-300 text-xs mt-1">{weatherError}</span> : null}
            <button type="button" onClick={() => setLocation({ ...location })} className="mt-2 px-4 py-1.5 rounded-full text-xs bg-navy-700 border border-border hover:border-sky transition">
              {t(language, 'retry')}
            </button>
          </div>
        )}

        {!weatherError && risk && weather && <AlertBanner risk={risk} weather={weather} language={language} />}

        <div className="grid grid-cols-1 lg:grid-cols-[1.3fr_1fr] gap-4 items-stretch">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {weatherLoading ? (
              <SkeletonCard />
            ) : weatherError || !weather ? (
              <div className="bg-gradient-to-b from-navy-900 to-navy-800 border border-border rounded-2xl">
                <ErrorState language={language} onRetry={() => setLocation({ ...location })} />
              </div>
            ) : (
              <WeatherCard weather={weather} language={language} />
            )}
            {!weatherError && weather && (
              <ReactiveMap
                location={{ label: weather.location_label, lat: location.latitude, lon: location.longitude }}
                weather={weather}
                risks={assessment}
                uiState={uiState}
              />
            )}
            <div className="bg-gradient-to-b from-navy-900 to-navy-800 border border-border rounded-2xl p-4 flex flex-col">
              <div className="text-[11.5px] uppercase tracking-wide text-slate-300 font-semibold mb-1">
                {t(language, 'riskLevel')}
              </div>
              {riskLoading ? (
                <LoadingState language={language} height="h-40" label={t(language, 'loadingRisk')} />
              ) : (
                <RiskGauge
                  score={overall?.overall_score ?? risk?.score ?? 0}
                  level={overall?.overall_severity ?? risk?.level ?? 'low'}
                  explanation={overall ? t(language, 'roleLabel') + ': ' + t(language, `role_${overall.role}`) : null}
                />
              )}
            </div>
          </div>
          <ChatPanel
            language={language}
            latitude={location.latitude}
            longitude={location.longitude}
            scenario={scenario}
            role={role}
            weather={weather}
            riskLevel={uiState.riskTheme.level}
          />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[1.4fr_1fr] gap-4 items-stretch">
          <ForecastCard
            forecast={forecast}
            loading={forecastLoading}
            error={forecastError}
            language={language}
            onRetry={() => setLocation({ ...location })}
          />
          <RiskPanel
            assessment={assessment}
            loading={riskLoading}
            error={riskError}
            language={language}
            onRetry={() => setLocation({ ...location })}
          />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[1.2fr_.8fr] gap-4">
          <MapCard center={location} safeZones={safeZones} language={language} />
          <div className="grid grid-cols-1 gap-4">
            <SafetyTips scenario={scenario} language={language} />
            <SafeZonesList zones={safeZones} origin={location} language={language} />
          </div>
        </div>
          </>
        )}
      </div>

      <SosModal open={sosOpen} onClose={() => setSosOpen(false)} latitude={location.latitude} longitude={location.longitude} language={language} />
      <LanguageModal
        open={langOpen}
        onClose={() => setLangOpen(false)}
        currentLang={language}
        onSelect={(code) => {
          onLanguageChange(code)
          setLangOpen(false)
        }}
      />

      {adminOpen && session.user.is_admin && (
        <AdminPanel language={language} session={session} onClose={() => setAdminOpen(false)} />
      )}
    </div>
    </WeatherAtmosphere>
  )
}
