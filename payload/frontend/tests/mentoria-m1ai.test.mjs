import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const page = fs.readFileSync("src/routes/MentoriaLanding.tsx", "utf8");
const widget = fs.readFileSync("src/routes/MentoriaAssistant.tsx", "utf8");
const css = fs.readFileSync("src/routes/MentoriaAssistant.css", "utf8");
const env = fs.readFileSync("src/vite-env.d.ts", "utf8");

test("commercial assistant is feature gated and independently namespaced", () => {
  assert.match(widget, /VITE_MENTORIA_ASSISTANT_ENABLED === "true"/);
  assert.match(widget, /securePrivacyUrl/);
  assert.match(env, /VITE_MENTORIA_ASSISTANT_ENABLED/);
  assert.match(page, /<MentoriaAssistant \/>/);
  assert.match(css, /^\.dg-mentoria \.dg-mentor-ai/m);
});
test("public questions cannot pass through privileged session or fake purchase", () => {
  assert.match(widget, /credentials: "omit"/);
  assert.match(widget, /\/api\/v2\/public\/mentoria\/assistant/);
  assert.doesNotMatch(widget, /sessionStorage|localStorage|Authorization:|Bearer |tenant_id|role_id/);
  assert.doesNotMatch(widget, /checkout_id|payment_approved|granted:/);
});
test("explicit AI acknowledgement, no XSS insertion, no PII fields, no fake success", () => {
  assert.match(widget, /ai_processing_acknowledged: true/);
  assert.match(widget, /no_sensitive_data_acknowledged: true/);
  assert.match(widget, /disabled=\{busy \|\| !acknowledged/);
  assert.match(widget, /response.status !== 200/);
  assert.match(widget, /role="alert"/);
  assert.doesNotMatch(widget, /dangerouslySetInnerHTML|innerHTML|<input[^>]+email/);
});
test("landing keeps M1 as sole contact registration", () => {
  assert.match(page, /<WorkshopRegistrationForm \/>/);
  assert.match(widget, /href="#workshop"/);
  assert.doesNotMatch(widget, /workshop-registrations|marketing_opt_in/);
});
