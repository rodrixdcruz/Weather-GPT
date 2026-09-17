// One-shot capture script for README screenshots. Drives system Chrome
// headless against the local dev server and saves three PNGs into
// docs/screenshots/: the login screen, the weather dashboard, and the map
// with an active shelter route. puppeteer-core is installed --no-save, so
// this leaves no dependency footprint in package.json.
import puppeteer from 'puppeteer-core'

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const BASE = 'http://localhost:5173'
const OUT = '../docs/screenshots'
const VIEWPORT = { width: 1440, height: 900, deviceScaleFactor: 2 }

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--no-sandbox', '--disable-dev-shm-usage', '--window-size=1440,900'],
})

try {
  const page = await browser.newPage()
  await page.setViewport(VIEWPORT)

  // ---- 1. Login screen (pristine, before typing) ----
  await page.goto(BASE, { waitUntil: 'networkidle2', timeout: 45000 })
  await sleep(2500) // fonts + animated weather backdrop settle
  await page.screenshot({ path: `${OUT}/login.png` })
  console.log('captured login.png')

  // ---- Log in as demo/customer to reach the dashboard ----
  await page.waitForSelector('input[autocomplete="username"]', { timeout: 15000 })
  await page.type('input[autocomplete="username"]', 'demo', { delay: 10 })
  await page.type('input[type="password"]', 'demo123', { delay: 10 })
  // pick the Customer role card (first radio in the role grid)
  await page.click('div[role="radiogroup"] button[role="radio"]')
  await sleep(300)
  await page.click('button[type="submit"]')
  // dashboard loads weather/risk/forecast from the live backend
  await page.waitForSelector('.leaflet-container', { timeout: 60000 })
  await sleep(6000) // weather, forecast, 3D avatar and map tiles settle

  // ---- 2. Dashboard with weather + risk + 3D avatar ----
  await page.screenshot({ path: `${OUT}/dashboard.png` })
  console.log('captured dashboard.png')

  // ---- 3. Map routing: click the first shelter's in-app Directions ----
  // Scroll the shelter list into view and click its first Directions button.
  await page.evaluate(() => {
    const btns = [...document.querySelectorAll('button')]
    const d = btns.find((b) => b.textContent.includes('Directions'))
    d?.scrollIntoView({ block: 'center' })
    return !!d
  })
  await sleep(600)
  await page.evaluate(() => {
    const btns = [...document.querySelectorAll('button')]
    btns.find((b) => b.textContent.includes('Directions'))?.click()
  })
  // wait for the OSRM route panel to appear with distance/ETA text
  await page.waitForFunction(
    () => document.body.innerText.includes('km ·'),
    { timeout: 30000 },
  )
  await sleep(2500) // flyToBounds animation finishes
  await page.screenshot({ path: `${OUT}/map-routing.png` })
  console.log('captured map-routing.png')
} finally {
  await browser.close()
}
