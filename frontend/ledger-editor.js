export const TRANSACTION_FIELDS = {
  BUY: { security: true, quantity: true, fees: true },
  SELL: { security: true, quantity: true, fees: true },
  DIVIDEND: { security: true, quantity: false, fees: true },
  CASH_DEPOSIT: { security: false, quantity: false, fees: false },
  CASH_WITHDRAWAL: { security: false, quantity: false, fees: false },
};

export function ledgerError(rows) {
  for (let index = 0; index < rows.length; index++) {
    const row = rows[index];
    const fields = TRANSACTION_FIELDS[row.transaction_type];
    const error = (field, message) => ({ index, field, message: `Transaction ${index + 1}: ${message}` });
    if (!fields) return error('type', 'choose a transaction type.');
    const day = new Date(`${row.transaction_date}T00:00:00Z`);
    if (!row.transaction_date || !Number.isFinite(day.getTime()) || day.toISOString().slice(0, 10) !== row.transaction_date) return error('date', 'choose a valid transaction date.');
    if (fields.security && !row.security_id) return error('security', 'choose a security.');
    for (const [key, label] of [['quantity', 'quantity'], ['cash_amount', 'transaction total'], ['fees', 'fees']]) {
      const value = row[key];
      if (typeof value !== 'string' || !/^\d+(\.\d+)?$/.test(value)) return error(key === 'cash_amount' ? 'cash' : key, `enter a non-negative ${label}.`);
    }
    if (fields.quantity && !/[1-9]/.test(row.quantity)) return error('quantity', 'quantity must be greater than zero.');
    if (!/^[A-Z]{3}$/.test(row.currency)) return error('currency', 'choose a currency.');
  }
  return null;
}
