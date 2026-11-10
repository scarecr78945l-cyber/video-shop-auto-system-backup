// Probe actual config and installed parsers; memory-only, no database deployment.
import assert from "node:assert/strict";
import { pathToFileURL, fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const frontend = path.resolve(here, "../../../frontend");
const { auth } = await import(pathToFileURL(path.join(frontend, "auth.config.ts")));
const { parseUserInput } = await import(pathToFileURL(path.join(frontend, "node_modules/better-auth/dist/db/schema.mjs")));
const ctx = await auth.$context;
const field = auth.options.user.additionalFields.status;
assert.equal(field.defaultValue, "active");
assert.equal(field.input, false);
assert.equal(field.required, true);
const created = parseUserInput(auth.options, { status: "disabled" }, "create");
assert.equal(created.status, "active");
let updateDenied = false;
try {
  parseUserInput(auth.options, { status: "disabled" }, "update");
} catch (error) {
  updateDenied = error.status === "BAD_REQUEST";
}
assert.ok(updateDenied);
const ids = Array.from({ length: 5 }, () => ctx.generateId({ model: "user" }));
assert.ok(ids.every(id => /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(id)));
console.log("STATUS_CONFIG=required/default_active/input_false");
console.log("CLIENT_CREATE_STATUS=active");
console.log("CLIENT_UPDATE_STATUS=BAD_REQUEST");
console.log("GENERATED_UUID_V4=5/5");
console.log("DATABASE_CONFIGURED=" + Boolean(auth.options.database));
console.log("PROBE_SCOPE=config_and_parser_only_no_real_IdP");
