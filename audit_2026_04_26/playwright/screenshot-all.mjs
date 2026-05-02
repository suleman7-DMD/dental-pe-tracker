import { chromium } from '@playwright/test';
import { mkdir } from 'fs/promises';

const BASE = process.env.BASE_URL || 'https://dental-pe-nextjs.vercel.app';
const OUT = process.env.OUT_DIR || '/Users/suleman/dental-pe-tracker/audit_2026_04_26/screenshots/baseline';

const ROUTES = [
  '/', '/launchpad', '/warroom', '/deal-flow', '/market-intel',
  '/buyability', '/job-market', '/research', '/intelligence',
  '/system', '/data-breakdown'
];

await mkdir(OUT, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();

const results = [];

for (const route of ROUTES) {
  const url = `${BASE}${route}`;
  const slug = route === '/' ? 'home' : route.slice(1).replace(/\//g, '_');
  const filepath = `${OUT}/${slug}.png`;
  console.log(`Capturing ${url} -> ${filepath}`);
  try {
    const response = await page.goto(url, { waitUntil: 'networkidle', timeout: 45000 });
    await page.waitForTimeout(2000); // let lazy content render
    await page.screenshot({ path: filepath, fullPage: true });
    const status = response?.status() ?? 0;
    const title = await page.title();
    results.push({ route, status, title, file: filepath });
  } catch (err) {
    console.error(`FAIL ${route}: ${err.message}`);
    results.push({ route, status: 'ERROR', error: err.message });
    try { await page.screenshot({ path: filepath.replace('.png', '-ERROR.png'), fullPage: true }); } catch (_) {}
  }
}

await browser.close();

console.log('\n=== SUMMARY ===');
for (const r of results) {
  console.log(`${r.status}\t${r.route}\t${r.title || r.error || ''}`);
}
