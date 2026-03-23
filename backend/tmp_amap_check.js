const { chromium } = require('playwright');
(async() => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  page.on('console', msg => console.log('CONSOLE::' + msg.type() + '::' + msg.text()));
  page.on('pageerror', err => console.log('PAGEERROR::' + err.message));
  page.on('requestfailed', req => console.log('REQFAILED::' + req.url() + '::' + req.failure()?.errorText));
  page.on('response', async res => {
    const url = res.url();
    if (url.includes('webapi.amap.com')) {
      console.log('AMAPRESP::' + res.status() + '::' + url);
      try {
        const text = await res.text();
        console.log('AMAPBODY::' + text.slice(0, 400));
      } catch (e) {}
    }
  });
  await page.goto('http://127.0.0.1:8025/login');
  await page.fill('input[name="username"]', 'admin');
  await page.fill('input[name="password"]', 'admin123');
  await Promise.all([
    page.waitForURL('http://127.0.0.1:8025/'),
    page.click('button[type="submit"]')
  ]);
  await page.waitForTimeout(3000);
  console.log('AMAPTYPE::' + await page.evaluate(() => typeof window.AMap));
  console.log('GPSSTATUS::' + await page.locator('#gps-status').textContent());
  await page.screenshot({ path: 'E:/Code/Project4/fastapi/playwright-amap.png', fullPage: true });
  await browser.close();
})();
