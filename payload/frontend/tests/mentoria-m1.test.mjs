import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const page = fs.readFileSync("src/routes/MentoriaLanding.tsx", "utf8");
const form = fs.readFileSync("src/routes/WorkshopRegistrationForm.tsx", "utf8");
const css = fs.readFileSync("src/routes/WorkshopRegistrationForm.css", "utf8");
const env = fs.readFileSync("src/vite-env.d.ts", "utf8");

test("M1 form is guarded by explicit flag and a secure privacy notice", () => {
  assert.match(form, /VITE_MENTORIA_REGISTRATION_ENABLED === "true"/);
  assert.match(form, /url.protocol !== "https:"/);
  assert.match(form, /url.username \|\| url.password/);
  assert.match(form, /VITE_MENTORIA_PRIVACY_VERSION/);
  assert.match(page, /formEnabled \? \(/);
  assert.match(page, /registrationUrl \? \(/);
  assert.match(env, /readonly VITE_MENTORIA_PRIVACY_URL/);
});

test("Public registration is stateless and does not escalate platform session", () => {
  assert.match(form, /credentials: "omit"/);
  assert.doesNotMatch(form, /sessionStorage|localStorage|authorization|Bearer|tenant_id|role_id/);
  assert.match(form, /\/api\/v2\/public\/mentoria\/workshop-registrations/);
  assert.doesNotMatch(form, /paid:\s*true|payment_approved|enrollment_id/);
});

test("Success requires accepted HTTP 202, errors remain visible", () => {
  assert.match(form, /response\.status !== 202/);
  assert.match(form, /setStatus\("error"\)/);
  assert.match(form, /role=\{status === "error" \? "alert" : "status"\}/);
});

test("Privacy acknowledgement, distinct marketing choice and bot trap are present", () => {
  assert.match(form, /privacy_accepted: accepted/);
  assert.match(form, /marketing_opt_in: marketing/);
  assert.match(form, /website,/);
  assert.match(form, /type="checkbox" required checked=\{accepted\}/);
  assert.match(form, /type="checkbox" checked=\{marketing\}/);
  assert.match(form, /autoComplete="email"/);
  assert.match(css, /^\.dg-mentoria /m);
});
