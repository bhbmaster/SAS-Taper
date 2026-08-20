/* Shared browser discovery for the Node test suites.
 *
 * playwright-core deliberately ships no browser, so find one: an explicit
 * CHROMIUM_PATH first, then a Playwright download cache (Linux and macOS
 * defaults), then whatever Chrome or Chromium is already installed.
 *
 * test_layout.js is the only suite that needs a browser — it measures a
 * rendered page, which nothing else can do. test_parity.js used to need one
 * too, before the maths moved into a generated block it can lift out of
 * index.html and run in Node directly.
 *
 * The suite must skip cleanly when there is no browser, so a bare checkout
 * still passes; CI closes that hole with an explicit findBrowser() gate.
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
   Callers should exit 0 on null — a checkout without a browser must not fail
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

module.exports = { findBrowser, launchOrSkip, PAGE: "file://" + path.join(__dirname, "index.html") };
