// Drive the running web app in headless Chrome: open a draft class, check the
// engine toggle and the Pre-dem columns, open the top player's card and read
// its score ledger, then switch to legacy and check the ledger is gone.
//
//   node .claude/skills/run-ootp-dev/drive.mjs CLASS OUT_DIR [BASE_URL]
//
// Screenshots land in OUT_DIR. Exits 1 if a check fails or the page logs an
// error. CHROME overrides the browser binary (default: macOS Google Chrome).
import { chromium } from 'playwright-core';

const [klass, out, base = 'http://localhost:8091'] = process.argv.slice(2);
if (!klass || !out) {
  console.error('usage: drive.mjs CLASS OUT_DIR [BASE_URL]');
  process.exit(2);
}
const chrome = process.env.CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

const failures = [];
const check = (ok, what) => {
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${what}`);
  if (!ok) failures.push(what);
};

const browser = await chromium.launch({ executablePath: chrome, headless: true });
const page = await (await browser.newContext({ viewport: { width: 1400, height: 1000 } })).newPage();
const errors = [];
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
page.on('pageerror', (e) => errors.push(String(e)));
// The SPA always shows its login form until it holds a token; with
// APP_PASSWORD unset the server accepts any credentials.
await page.addInitScript(() => sessionStorage.setItem('ootp-draft-auth', 'Basic ' + btoa('u:p')));

const firstRow = () => page.locator('tr.body-row').first();
const openTopCard = async () => {
  await firstRow().click();
  await page.waitForSelector('.model-col', { timeout: 15000 });
};

try {
  // --- v2 (the default engine)
  await page.goto(`${base}/class/${klass}`);
  await firstRow().waitFor({ timeout: 30000 });
  const top = (await firstRow().innerText()).split(/[\t\n]/).map((s) => s.trim()).filter(Boolean);
  console.log('top row:', top.slice(0, 10).join(' | '));
  await page.screenshot({ path: `${out}/1-table-v2.png` });
  check((await page.locator('.engine-toggle button.active').innerText()) === 'v2', 'toggle defaults to v2');
  const headers = await page.locator('th').allInnerTexts();
  check(headers.some((h) => h.includes('Pre-dem')), 'Pre-dem columns shown');

  await openTopCard();
  await page.waitForSelector('.ledger', { timeout: 15000 });
  await page.locator('.model-col').screenshot({ path: `${out}/2-card-v2.png` });
  const rows = await page.locator('.ledger-row').count();
  const total = await page.locator('.ledger-row.total b').innerText();
  console.log(`ledger: ${rows} rows, total ${total}`);
  check(rows > 2, 'card shows the score ledger');

  // --- legacy: the toggle reloads the page
  await Promise.all([page.waitForNavigation(), page.click('.engine-toggle button:has-text("legacy")')]);
  await firstRow().waitFor({ timeout: 30000 });
  check((await page.locator('.engine-toggle button.active').innerText()) === 'legacy', 'toggle switched to legacy');
  await page.screenshot({ path: `${out}/3-table-legacy.png` });
  await openTopCard();
  await page.waitForTimeout(1500); // the breakdown query lands after the card opens
  await page.locator('.model-col').screenshot({ path: `${out}/4-card-legacy.png` });
  check((await page.locator('.ledger').count()) === 0, 'legacy card has no ledger');
} catch (e) {
  failures.push(String(e));
  console.log('FAIL', e.message);
  await page.screenshot({ path: `${out}/error.png` }).catch(() => {});
} finally {
  await browser.close();
}

check(errors.length === 0, `no console errors${errors.length ? ': ' + errors.join(' / ') : ''}`);
console.log(`screenshots in ${out}`);
process.exit(failures.length ? 1 : 0);
