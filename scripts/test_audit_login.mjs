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

  console.log('Navigating to http://localhost:3000/auth/login...');
  await page.goto('http://localhost:3000/auth/login', { waitUntil: 'networkidle' });

  console.log('Filling credentials...');
  await page.fill('#login-email', 'james@company.com');
  await page.fill('#login-password', 'admin123!');
  await page.click('button[type="submit"]');

  console.log('Waiting for navigation or url change...');
  await page.waitForTimeout(3000);
  console.log('Current URL after login:', page.url());

  const cookies = await context.cookies();
  console.log('Cookies received:', cookies.map(c => c.name));

  await browser.close();
}

run().catch(console.error);
