import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const app = fs.readFileSync("src/App.tsx", "utf8");
const page = fs.readFileSync("src/routes/MentoriaLanding.tsx", "utf8");
const css = fs.readFileSync("src/routes/MentoriaLanding.css", "utf8");
const types = fs.readFileSync("src/vite-env.d.ts", "utf8");

test("Mentoria route is additive and does not replace EFATA public/private routes", () => {
  assert.match(app, /path="\/" element={<Landing \/>}/);
  assert.match(app, /path="\/mentoria" element={<MentoriaLanding \/>}/);
  assert.match(app, /path="\/app" element={<AppEntry \/>}/);
  assert.match(app, /path="\/admin" element={<AdminAccessGate \/>}/);
  assert.match(app, /path="\/activate" element={<PlatformInviteAccept \/>}/);
});

test("Workshop CTA only accepts a configured HTTPS URL without embedded credentials", () => {
  assert.match(page, /url\.protocol !== "https:"/);
  assert.match(page, /url\.username \|\| url\.password/);
  assert.match(page, /rel="noopener noreferrer"/);
  assert.match(page, /VITE_MENTORIA_WORKSHOP_URL/);
  assert.match(types, /readonly VITE_MENTORIA_WORKSHOP_URL\?: string/);
});

test("No fake billing, enrollment, tenancy or storage in the public landing", () => {
  assert.doesNotMatch(page, /\bfetch\s*\(/);
  assert.doesNotMatch(page, /\blocalStorage\b|\bsessionStorage\b/);
  assert.doesNotMatch(page, /\/api\/v2\/billing|asaas|checkout_id/);
  assert.doesNotMatch(page, /tenant_id|role_id|paid:\s*true/);
  assert.match(page, /Inscrições em preparação/);
});

test("Mentoria has distinct scope, accessibility and responsible offer", () => {
  assert.match(page, /<main id="main-content"/);
  assert.match(page, /<h1 id="dg-hero-title"/);
  assert.match(page, /<nav[^>]+aria-label=/);
  assert.match(page, /<details key=/);
  assert.match(page, /6 horas de encontros coletivos/);
  assert.match(page, /1 hora individual posterior/);
  assert.match(page, /não equivale automaticamente à contratação/);
  assert.match(css, /^\.dg-mentoria/m);
  assert.doesNotMatch(css, /^\s*(body|html|:root|h1)\s*\{/m);
});
