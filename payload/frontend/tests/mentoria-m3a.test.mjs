import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const app = fs.readFileSync("src/App.tsx", "utf8");
const landing = fs.readFileSync("src/routes/MentoriaLanding.tsx", "utf8");
const portal = fs.readFileSync("src/routes/MentoriaPortal.tsx", "utf8");
const access = fs.readFileSync("src/routes/AccessPortal.tsx", "utf8");
const css = fs.readFileSync("src/routes/MentoriaPortal.css", "utf8");

test("private portal is routed separately from the public landing", () => {
  assert.match(app, /path="\/mentoria\/area"/);
  assert.match(landing, /<Link to="\/mentoria\/area">Área do mentorado<\/Link>/);
  assert.match(css, /^\.dg-portal/m);
});

test("portal always fetches backend authorization and never holds privileged identities", () => {
  assert.match(portal, /apiJson<PortalResponse>\("\/api\/v2\/mentoria\/portal\/me"\)/);
  assert.doesNotMatch(portal, /localStorage|sessionStorage|Authorization:|Bearer |tenant_id|member_id|role_id/);
  assert.doesNotMatch(portal, /dangerouslySetInnerHTML|innerHTML/);
});

test("no fake class videos, meeting links or checkout confirmations", () => {
  assert.match(portal, /após a publicação oficial/);
  assert.doesNotMatch(portal, /iframe|<video|checkout|paid: true|success: true|payment_approved/);
});

test("login return path only adds a fixed portal URL", () => {
  assert.match(access, /if \(clean === "\/mentoria\/area"\) return clean;/);
  assert.match(portal, /\/access\?next=%2Fmentoria%2Farea/);
});

test("all auth states are explicit and fail closed", () => {
  for (const key of ['"loading"', '"ready"', '"login"', '"denied"', '"disabled"', '"error"']) {
    assert.ok(portal.includes(key), key);
  }
  assert.match(portal, /response\.programs/);
});
