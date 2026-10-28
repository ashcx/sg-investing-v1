import assert from 'node:assert/strict';
import { ledgerError, TRANSACTION_FIELDS } from '../ledger-editor.js';
import { createLedgerStore, createMemoryDriver, parseLedgerPayload } from '../ledger-store.js';
const row = { transaction_type: 'BUY', security_id: 'test', transaction_date: '2024-01-02', quantity: '10', cash_amount: '100', fees: '2.50', currency: 'SGD' };
const store = createLedgerStore(createMemoryDriver());
await store.save([row]);
assert.deepEqual(await store.load(), [row]);
const preview = parseLedgerPayload(JSON.stringify({ schema: 'sg-invest-ledger', rows: [{ ...row, fees: '3.50', row_id: 'stable-1', transaction_id: 'original' }] }));
assert.equal(preview[0].fees, '3.50');
assert.deepEqual(await store.load(), [row], 'preview must not write storage');
await store.importJson(JSON.stringify(preview));
assert.deepEqual(parseLedgerPayload(await store.exportJson()), preview);
assert.equal(ledgerError([row]), null);
assert.equal(ledgerError([{ ...row, transaction_date: '2024-02-31' }]).field, 'date');
assert.equal(ledgerError([{ ...row, quantity: '-1' }]).field, 'quantity');
assert.equal(ledgerError([{ ...row, quantity: '0' }]).field, 'quantity');
assert.equal(ledgerError([{ ...row, cash_amount: '' }]).field, 'cash');
assert.equal(ledgerError([{ ...row, security_id: null }]).field, 'security');
for (const type of Object.keys(TRANSACTION_FIELDS)) {
  const fields = TRANSACTION_FIELDS[type];
  assert.equal(ledgerError([{ ...row, transaction_type: type, security_id: fields.security ? 'test' : null, quantity: fields.quantity ? '1' : '0' }]), null);
}
console.log('PASS ledger editor: legacy round trip, preview purity, fee/ID preservation, all types, date and numeric errors.');
assert.throws(() => parseLedgerPayload([{ ...row, row_id: 'duplicate' }, { ...row, row_id: 'duplicate' }]), /duplicate row_id/);
const failingStore = createLedgerStore({ name: 'failure', read: async () => ({ rows: [row] }), write: async () => { throw new Error('quota exceeded'); }, remove: async () => {} });
await assert.rejects(failingStore.save([row]), /quota exceeded/);
assert.deepEqual(await failingStore.load(), [row]);
console.log('PASS duplicate identity rejection and explicit storage write failure.');
