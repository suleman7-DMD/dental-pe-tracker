/**
 * final-qa.mjs — Final QA verification for dental-pe-tracker
 * Captures home, warroom, launchpad, intelligence with console error collection.
 * Viewport: 1920×1080. Waits for network idle + lazy loads.
 */
import { chromium } from '@playwright/test';
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
    // Extra wait for lazy content
    await page.waitForTimeout(3000);

    // Scroll to bottom and back to trigger lazy loads
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(1500);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(1000);

    if (extraFn) {
      await extraFn(page).catch(e => console.error(`Extra fn error: ${e.message}`));
    }

    // Full page screenshot
    await page.screenshot({ path: `${OUT}/${slug}.png`, fullPage: true });
    // Also viewport screenshot
    await page.screenshot({ path: `${OUT}/${slug}-viewport.png`, fullPage: false });

    results[slug] = { status, title, consoleErrors, consoleWarnings, url };
    console.log(`  HTTP ${status} | Title: ${title}`);
    console.log(`  Console errors: ${consoleErrors.length}`);
    if (consoleErrors.length) consoleErrors.forEach(e => console.log(`    ERROR: ${e}`));
  } catch (err) {
    console.error(`  FAIL: ${err.message}`);
    try { await page.screenshot({ path: `${OUT}/${slug}-ERROR.png`, fullPage: true }); } catch (_) {}
    results[slug] = { status: 'ERROR', error: err.message, consoleErrors, consoleWarnings, url };
  }

  await page.close();
  return results[slug];
}

// ─── HOME ───────────────────────────────────────────────────────────────────
await capturePage('home', '/', async (page) => {
  // Extract KPI card text
  const kpiText = await page.evaluate(() => {
    const cards = Array.from(document.querySelectorAll('[data-testid="kpi-card"], .kpi-card, [class*="kpi"]'));
    return cards.map(c => c.innerText).join('\n---\n');
  });
  console.log('  KPI cards text (raw):', kpiText.slice(0, 500));

  // Check activity feed
  const feedText = await page.evaluate(() => {
    const feed = document.querySelector('[class*="activity"], [class*="recent"], [data-testid="activity-feed"]');
    return feed ? feed.innerText.slice(0, 500) : 'NOT FOUND';
  });
  console.log('  Activity feed:', feedText.slice(0, 300));

  // Extract all visible numbers (KPIs) from the page body
  const bodyText = await page.evaluate(() => document.body.innerText.slice(0, 3000));
  console.log('  Body text (first 3000):', bodyText);
});

// ─── WARROOM ─────────────────────────────────────────────────────────────────
await capturePage('warroom', '/warroom', async (page) => {
  // Extract sitrep / KPI strip text
  const sitrep = await page.evaluate(() => {
    const strip = document.querySelector('[class*="sitrep"], [class*="kpi-strip"], [data-testid="sitrep"]');
    return strip ? strip.innerText : 'SITREP STRIP NOT FOUND';
  });
  console.log('  Sitrep strip:', sitrep.slice(0, 500));

  // Count target list items
  const targetCount = await page.evaluate(() => {
    const items = document.querySelectorAll('[class*="target-item"], [class*="practice-row"], [class*="list-item"]');
    return items.length;
  });
  console.log('  Target list items found:', targetCount);

  // Check signal overlay buttons
  const signalButtons = await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    return btns.filter(b => ['stealth_dso','phantom_inventory','family_dynasty','micro_cluster','retirement_combo','last_change_90d','high_peer_retirement','revenue_default'].some(s => b.innerText.toLowerCase().includes(s.toLowerCase().replace(/_/g,' ')) || b.getAttribute('data-signal') === s)).map(b => b.innerText.trim());
  });
  console.log('  Signal buttons found:', JSON.stringify(signalButtons));

  // Full body text for manual review
  const bodyText = await page.evaluate(() => document.body.innerText.slice(0, 4000));
  console.log('  Warroom body (4000):', bodyText);

  // Try clicking stealth_dso if button found
  try {
    const stealthBtn = await page.$('button[data-signal="stealth_dso"], button:has-text("Stealth"), button:has-text("stealth")');
    if (stealthBtn) {
      await stealthBtn.click();
      await page.waitForTimeout(2000);
      await page.screenshot({ path: `${OUT}/warroom-stealth-overlay.png`, fullPage: false });
      console.log('  stealth_dso overlay clicked, screenshot taken');
    } else {
      console.log('  stealth_dso button not found via selector');
    }
  } catch (e) {
    console.log('  stealth_dso click error:', e.message);
  }
});

// ─── LAUNCHPAD ───────────────────────────────────────────────────────────────
await capturePage('launchpad', '/launchpad', async (page) => {
  const bodyText = await page.evaluate(() => document.body.innerText.slice(0, 4000));
  console.log('  Launchpad body (4000):', bodyText);

  // Check for "Structural record only" occurrences
  const structuralCount = await page.evaluate(() => {
    const text = document.body.innerText;
    return (text.match(/structural record only/gi) || []).length;
  });
  console.log('  "Structural record only" count:', structuralCount);

  // Check compound thesis tab
  const tabs = await page.evaluate(() => {
    const tabs = Array.from(document.querySelectorAll('[role="tab"], button[class*="tab"]'));
    return tabs.map(t => t.innerText.trim());
  });
  console.log('  Tabs found:', JSON.stringify(tabs));
});

// ─── INTELLIGENCE ─────────────────────────────────────────────────────────────
await capturePage('intelligence', '/intelligence', async (page) => {
  const bodyText = await page.evaluate(() => document.body.innerText.slice(0, 4000));
  console.log('  Intelligence body (4000):', bodyText);

  // Check for citation markers like <cite index="N-M">
  const citeCount = await page.evaluate(() => {
    const html = document.body.innerHTML;
    return (html.match(/<cite\s/gi) || []).length;
  });
  const citeTextCount = await page.evaluate(() => {
    const text = document.body.innerText;
    return (text.match(/\[cite|<cite/gi) || []).length;
  });
  console.log('  <cite> HTML tags:', citeCount, '| visible cite text patterns:', citeTextCount);

  // Check KPIs
  const kpis = await page.evaluate(() => {
    const els = Array.from(document.querySelectorAll('[class*="kpi"], [class*="metric"], [class*="stat"]'));
    return els.slice(0, 10).map(e => e.innerText.trim()).filter(Boolean);
  });
  console.log('  Intelligence KPIs:', JSON.stringify(kpis));
});

await browser.close();

// Save results JSON
await writeFile(`${OUT}/results.json`, JSON.stringify(results, null, 2));
console.log('\n\n=== FINAL RESULTS SAVED TO', `${OUT}/results.json`, '===');
console.log(JSON.stringify(results, null, 2));
