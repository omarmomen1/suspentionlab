import { chromium } from '@playwright/test';

async function run() {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  page.on('console', msg => console.log('BROWSER CONSOLE:', msg.type(), msg.text()));
  page.on('pageerror', err => console.log('BROWSER ERROR:', err.message));
  page.on('request', req => {
    if (req.url().includes(':8000') || req.url().includes('/api/')) {
      console.log('>> API REQ:', req.method(), req.url());
    }
  });
  page.on('response', async res => {
    if (res.url().includes(':8000') || res.url().includes('/api/')) {
      console.log('<< API RES:', res.status(), res.url());
    }
  });

  await page.goto('http://localhost:3000/auth/login', { waitUntil: 'networkidle' });
  await page.fill('#login-email', 'james@company.com');
  await page.fill('#login-password', 'admin123!');
  await page.click('button[type="submit"]');

  await page.waitForTimeout(4000);
  console.log('URL after wait:', page.url());

  console.log('Navigating to http://localhost:3000/...');
  await page.goto('http://localhost:3000/', { waitUntil: 'networkidle' });
  console.log('Title:', await page.title());
  console.log('Body text excerpt:', (await page.innerText('body')).slice(0, 300));

  await browser.close();
}

run().catch(console.error);
