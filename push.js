// Sends a Web Push notification to the stored subscription when the latest
// scrape found new jobs. Run by the GitHub workflow after daily_run.py.
// Self-skips (exit 0) if no subscription is configured or there are no new jobs,
// so it never fails the build.
const fs = require("fs");
const webpush = require("web-push");

const subRaw = process.env.PUSH_SUBSCRIPTION;
if (!subRaw) {
  console.log("No PUSH_SUBSCRIPTION secret — skipping push.");
  process.exit(0);
}

const pushFile = process.argv[2] || "push.json"; // which profile's payload to send
let payload;
try {
  payload = JSON.parse(fs.readFileSync(pushFile, "utf8"));
} catch (e) {
  console.log("No " + pushFile + " — skipping push.");
  process.exit(0);
}
if (!payload.count || payload.count < 1) {
  console.log("No new jobs this run — no push sent.");
  process.exit(0);
}

let subscription;
try {
  subscription = JSON.parse(subRaw);
} catch (e) {
  console.error("PUSH_SUBSCRIPTION is not valid JSON — skipping.");
  process.exit(0);
}

webpush.setVapidDetails(
  process.env.VAPID_SUBJECT || "mailto:codexkunal@gmail.com",
  process.env.VAPID_PUBLIC_KEY,
  process.env.VAPID_PRIVATE_KEY
);

webpush
  .sendNotification(subscription, JSON.stringify(payload))
  .then(() => console.log("Push sent:", payload.title))
  .catch((err) => {
    // 404 / 410 mean the subscription expired; log and continue without failing.
    console.error("Push failed:", err.statusCode, err.body || err.message);
    process.exit(0);
  });
