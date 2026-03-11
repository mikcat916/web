const fs = require("node:fs/promises");
const path = require("node:path");
const { chromium } = require("playwright");

const baseURL = process.env.BASE_URL || "http://127.0.0.1:8011";
const outputDir =
  process.env.OUT_DIR || path.join(process.cwd(), "artifacts", "playwright");
const chromePath =
  process.env.CHROME_PATH ||
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

const pages = [
  { id: "overview", path: "/" },
  { id: "tasks", path: "/_3" },
  { id: "reports", path: "/_1" },
  { id: "status", path: "/monitoring_dashboard" },
  { id: "maintenance", path: "/maintenance" },
  { id: "zones", path: "/zone_control" },
];

async function main() {
  await fs.mkdir(outputDir, { recursive: true });

  const browser = await chromium.launch({
    headless: true,
    executablePath: chromePath,
    args: ["--disable-gpu", "--no-first-run", "--no-default-browser-check"],
  });

  const page = await browser.newPage({
    viewport: { width: 1512, height: 982 },
    deviceScaleFactor: 1,
  });

  const report = [];

  for (let index = 0; index < pages.length; index += 1) {
    const target = pages[index];
    const consoleErrors = [];
    const pageErrors = [];

    const onConsole = (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    };
    const onPageError = (error) => {
      pageErrors.push(String(error));
    };

    page.on("console", onConsole);
    page.on("pageerror", onPageError);

    await page.goto(`${baseURL}${target.path}`, {
      waitUntil: "load",
      timeout: 30000,
    });

    await page.waitForTimeout(1200);

    const bodyText = await page.locator("body").innerText();
    const screenshotPath = path.join(
      outputDir,
      `${String(index + 1).padStart(2, "0")}-${target.id}.png`
    );
    await page.screenshot({ path: screenshotPath, fullPage: true });

    report.push({
      page: target.id,
      path: target.path,
      title: await page.title(),
      activeNav:
        (await page.locator(".nav-item.active").first().innerText().catch(() => "")) || "",
      containsNullText: bodyText.includes("null"),
      consoleErrors,
      pageErrors,
      screenshotPath,
    });

    page.off("console", onConsole);
    page.off("pageerror", onPageError);
  }

  await browser.close();

  const failures = report.filter(
    (item) => item.containsNullText || item.consoleErrors.length || item.pageErrors.length
  );

  const result = { failures, report, outputDir };
  await fs.writeFile(path.join(outputDir, "report.json"), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result, null, 2));

  if (failures.length) {
    process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
