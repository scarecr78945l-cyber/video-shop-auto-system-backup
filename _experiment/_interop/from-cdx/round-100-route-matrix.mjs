// Guard contract checks; real-cookie fixtures are replayed separately.
import assert from 'node:assert/strict';
import { auth, handler } from '../../../frontend/auth.config.ts';

const names = ['create', 'update', 'delete', 'set-active', 'invite-member',
  'cancel-invitation', 'accept-invitation', 'reject-invitation', 'add-member',
  'update-member-role', 'remove-member', 'leave', 'create-team', 'update-team',
  'remove-team', 'add-team-member', 'remove-team-member'];
const base = auth.options.baseURL;
let count = 0;
for (const name of names) {
  for (const method of ['POST', 'PUT', 'PATCH', 'DELETE']) {
    const response = await handler(new Request(`${base}/api/auth/organization/${name}`, {
      method, headers: { origin: base, 'content-type': 'application/json' }, body: '{}',
    }));
    assert.equal(response.status, 403, `${method} ${name}`);
    count++;
  }
}
console.log('GUARD_CASES_PASS=' + count);
for (const path of ['/api/auth/organization/%6ceave', '/api/auth/organization//leave',
  '/api/auth/organization/leave/', '/api/auth/organization/leave?x=1']) {
  const response = await handler(new Request(base + path, {
    method: 'POST', headers: { origin: base, 'content-type': 'application/json' }, body: '{}',
  }));
  assert.ok([403, 404].includes(response.status));
  console.log('PATH=' + JSON.stringify({ path, status: response.status }));
}
const read = await handler(new Request(base + '/api/auth/organization/list', { headers: { origin: base } }));
assert.equal(read.status, 401);
console.log('READ_REACHES_SESSION_CHECK=' + read.status);
