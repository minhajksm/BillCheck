// Renders the Play listing images from assets.html. Needs app/node_modules
// installed (for the Mukta font) and Playwright with Chromium.
// Run from the repository root: node docs/play-store/render.js
// Play asks for the icon as a 32-bit PNG and Chromium writes an opaque one as
// 24-bit, so the committed icon-512.png was then converted to RGBA:
//   python3 -c "from PIL import Image; p='docs/play-store/icon-512.png'; Image.open(p).convert('RGBA').save(p)"
const path = require('path');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1100, height: 1100 } });
  await page.goto('file://' + path.join(__dirname, 'assets.html'));
  await page.evaluate(() => document.fonts.ready);
  await page.locator('#icon').screenshot({ path: path.join(__dirname, 'icon-512.png') });
  await page.locator('#feature').screenshot({ path: path.join(__dirname, 'feature-graphic-1024x500.png') });
  await browser.close();
})();
