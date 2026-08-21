/* Shared browser discovery for the Node test suites.
 *
 * playwright-core deliberately ships no browser, so find one: an explicit
 * CHROMIUM_PATH first, then a Playwright download cache (Linux and macOS
 * defaults), then whatever Chrome or Chromium is already installed.
 *
 * Both test_parity.js and test_layout.js need a browser and both must skip
 * cleanly without one, so the logic lives here rather than in each.
 */

"use strict";

const fs = require("fs");
const path = require("path");

function findBrowser() {
  const envPath = process.env.CHROMIUM_PATH;
  if (envPath && fs.existsSync(envPath)) return envPath;

  const home = process.env.HOME || "";
  const caches = [
    process.env.PLAYWRIGHT_BROWSERS_PATH,
    "/opt/pw-browsers",
    home && path.join(home, ".cache/ms-playwright"),
    home && path.join(home, "Library/Caches/ms-playwright"),
  ].filter(Boolean);
  const rels = [
    "chrome-linux/chrome",
    "chrome-linux/headless_shell",
    "chrome-mac/Chromium.app/Contents/MacOS/Chromium",
    "chrome-mac-arm64/Chromium.app/Contents/MacOS/Chromium",
    "chrome-headless-shell-mac/chrome-headless-shell",
  ];
  for (const root of caches) {
    if (!fs.existsSync(root)) continue;
    for (const d of fs.readdirSync(root)) {
      for (const rel of rels) {
        const p = path.join(root, d, rel);
        if (fs.existsSync(p)) return p;
      }
    }
  }

  for (const p of [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/snap/bin/chromium",
  ]) {
    if (fs.existsSync(p)) return p;
  }
  return null;
}

/* Returns a launched browser, or null after printing why it is skipping.
   Callers should exit 0 on null. A checkout without a browser must not fail
   the suite. */
async function launchOrSkip() {
  let chromium;
  try {
    ({ chromium } = require("playwright-core"));
  } catch (e) {
    console.log("skipped: playwright-core is not installed (npm i -D playwright-core)");
    return null;
  }
  const executablePath = findBrowser();
  if (!executablePath) {
    console.log("skipped: no Chromium found (set CHROMIUM_PATH or PLAYWRIGHT_BROWSERS_PATH)");
    return null;
  }
  return chromium.launch({ executablePath, args: ["--no-sandbox"] });
}

const fileUrl = (name) => "file://" + path.join(__dirname, name);

module.exports = {
  findBrowser,
  launchOrSkip,
  PAGE: fileUrl("index.html"),
  /* Algorithm explainers. Second and third shipped pages, so they get swept too. */
  FOLD_PAGE: fileUrl("fold.html"),
  LAG_PAGE: fileUrl("lag.html"),
};
