/**
 * final-qa2.mjs — Final QA verification for dental-pe-tracker
 * Captures home, warroom, launchpad, intelligence with console error collection.
 * Viewport: 1920x1080. Waits for network idle + lazy loads.
 */
import { chromium } from 'playwright';
import { mkdir, writeFile } from 'fs/promises';

const BASE = process.env.BASE_URL || 'https://dental-pe-nextjs.vercel.app';
const OUT = '/Users/suleman/dental-pe-tracker/audit_2026_04_26/screenshots/final-qa';

await mkdir(OUT, { recursive: true });

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1920, height: 1080 },
});

const results = {};

async function capturePage(slug, route, extraFn) {
  const page = await context.newPage();
  const consoleErrors = [];
  const consoleWarnings = [];

  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
    if (msg.type() === 'warning') consoleWarnings.push(msg.text());
  });
  page.on('pageerror', err => consoleErrors.push(`[pageerror] ${err.message}`));

  const url = `${BASE}${route}`;
  console.log(`\n=== ${slug.toUpperCase()} === ${url}`);

  let status = 0;
  let title = '';
  try {
    const resp = await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
    status = resp?.status() ?? 0;
    title = await page.title();
    await page.waitForTimeout(3000);

    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(1500);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(1000);

    if (extraFn) {
      await extraFn(page).catch(e => console.error(`Extra fn error: ${e.message}`));
    }

    await page.screenshot({ path: `${OUT}/${slug}.png`, fullPage: true });
    await page.screenshot({ path: `${OUT}/${slug}-viewport.png`, fullPage: false });

    results[slug] = { status, title, consoleErrors, consoleWarnings, url };
    console.log(`  HTTP ${status} | Title: ${title}`);
    console.log(`  Console errors: ${consoleErrors.length}`);
    if (consoleErrors.length) consoleErrors.slice(0,5).forEach(e => console.log(`    ERR: ${e.slice(0,200)}`));
  } catch (err) {
    console.error(`  FAIL: ${err.message}`);
    try { await page.screenshot({ path: `${OUT}/${slug}-ERROR.png`, fullPage: true }); } catch (_) {}
    results[slug] = { status: 'ERROR', error: err.message, consoleErrors, consoleWarnings, url };
  }

  await page.close();
  return results[slug];
}

// HOME
await capturePage('home', '/', async (page) => {
  const bodyText = await page.evaluate(() => document.body.innerText.slice(0, 3000));
  console.log('  Body text:', bodyText);
});

// WARROOM
await capturePage('warroom', '/warroom', async (page) => {
  const bodyText = await page.evaluate(() => document.body.innerText.slice(0, 4000));
  console.log('  Warroom body:', bodyText);

  const allBtns = await page.evaluate(() =>
    Array.from(document.querySelectorAll('button')).map(b => b.innerText.trim()).filter(Boolean)
  );
  console.log('  Buttons:', JSON.stringify(allBtns.slice(0, 40)));

  // Try clicking stealth button
  try {
    const stealthHandle = await page.evaluateHandle(() =>
      Array.from(document.querySelectorAll('button')).find(b =>
        b.innerText.toLowerCase().includes('stealth')
      )
    );
    const el = stealthHandle.asElement();
    if (el) {
      await el.click();
      await page.waitForTimeout(2000);
      await page.screenshot({ path: `${OUT}/warroom-stealth-overlay.png`, fullPage: false });
      console.log('  Stealth overlay screenshot taken');
    } else {
      console.log('  Stealth button NOT found in DOM');
    }
  } catch (e) {
    console.log('  Stealth click error:', e.message);
  }
});

// LAUNCHPAD
await capturePage('launchpad', '/launchpad', async (page) => {
  const bodyText = await page.evaluate(() => document.body.innerText.slice(0, 4000));
  console.log('  Launchpad body:', bodyText);

  const structuralCount = await page.evaluate(() =>
    (document.body.innerText.match(/structural record only/gi) || []).length
  );
  console.log('  "Structural record only" count:', structuralCount);

  const tabs = await page.evaluate(() =>
    Array.from(document.querySelectorAll('[role="tab"]')).map(t => t.innerText.trim())
  );
  console.log('  Tabs:', JSON.stringify(tabs));
});

// INTELLIGENCE
await capturePage('intelligence', '/intelligence', async (page) => {
  const bodyText = await page.evaluate(() => document.body.innerText.slice(0, 4000));
  console.log('  Intelligence body:', bodyText);

  const citeHtml = await page.evaluate(() =>
    (document.body.innerHTML.match(/<cite[\s>]/gi) || []).length
  );
  const citeVisible = await page.evaluate(() =>
    (document.body.innerText.match(/\[cite|<cite/gi) || []).length
  );
  console.log('  <cite> HTML tags:', citeHtml, '| visible cite patterns:', citeVisible);
});

await browser.close();

await writeFile(`${OUT}/results.json`, JSON.stringify(results, null, 2));
console.log('\n=== RESULTS JSON ===');
console.log(JSON.stringify(results, null, 2));
