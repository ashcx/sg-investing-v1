import { rateForDate } from './fx.js';
import { ZERO, dec } from './money.js';
import { AnalysisDataError, EngineValueError, TransactionType } from './models.js';

function lastCloseOnOrBefore(rows, securityId, asOf) {
  let last = null;
  for (const row of rows) {
    if (row.security_id === securityId && row.trading_date <= asOf) {
      if (last === null || row.trading_date > last.trading_date) last = row;
    }
  }
  if (last === null) {
    throw new AnalysisDataError(`No price on or before ${asOf} for security ${securityId}.`);
  }
  return last;
}

export function analyzePortfolio({ transactions, securities, prices, fxRates, asOf }) {
  const quantity = new Map();
  const costBasis = new Map();
  const realized = new Map();
  const cash = new Map();

  const mapDefault = (map, key) => {
    const existing = map.get(key);
    if (existing) return existing;
    map.set(key, ZERO);
    return ZERO;
  };

  const ordered = transactions
    .filter((item) => item.transaction_date <= asOf)
    .sort((a, b) => {
      if (a.transaction_date !== b.transaction_date) {
        return a.transaction_date < b.transaction_date ? -1 : 1;
      }
      return String(a.transaction_id) < String(b.transaction_id) ? -1 : 1;
    });

  for (const transaction of ordered) {
    const securityId = transaction.security_id;
    const type = transaction.transaction_type;
    if (type === TransactionType.BUY || type === TransactionType.SELL || type === TransactionType.DIVIDEND) {
      if (securityId == null || !securities[securityId]) {
        throw new EngineValueError('Security transaction refers to an unknown security.');
      }
      if (securities[securityId].currency !== transaction.currency) {
        throw new EngineValueError('Security transaction currency does not match security currency.');
      }
    }

    if (type === TransactionType.BUY) {
      quantity.set(securityId, mapDefault(quantity, securityId).plus(dec(transaction.quantity)));
      costBasis.set(
        securityId,
        mapDefault(costBasis, securityId).plus(dec(transaction.cash_amount)).plus(dec(transaction.fees)),
      );
      cash.set(
        transaction.currency,
        mapDefault(cash, transaction.currency).minus(dec(transaction.cash_amount)).minus(dec(transaction.fees)),
      );
    } else if (type === TransactionType.SELL) {
      const held = mapDefault(quantity, securityId);
      if (dec(transaction.quantity).gt(held)) {
        throw new EngineValueError('Cannot sell more shares than the weighted-average ledger holds.');
      }
      const averageCost = held.isZero() ? ZERO : mapDefault(costBasis, securityId).div(held);
      const disposedCost = averageCost.times(dec(transaction.quantity));
      const proceeds = dec(transaction.cash_amount).minus(dec(transaction.fees));
      realized.set(securityId, mapDefault(realized, securityId).plus(proceeds.minus(disposedCost)));
      quantity.set(securityId, held.minus(dec(transaction.quantity)));
      costBasis.set(securityId, mapDefault(costBasis, securityId).minus(disposedCost));
      cash.set(transaction.currency, mapDefault(cash, transaction.currency).plus(proceeds));
    } else if (type === TransactionType.DIVIDEND) {
      cash.set(
        transaction.currency,
        mapDefault(cash, transaction.currency).plus(dec(transaction.cash_amount)).minus(dec(transaction.fees)),
      );
    } else if (type === TransactionType.CASH_DEPOSIT) {
      cash.set(transaction.currency, mapDefault(cash, transaction.currency).plus(dec(transaction.cash_amount)));
    } else if (type === TransactionType.CASH_WITHDRAWAL) {
      cash.set(transaction.currency, mapDefault(cash, transaction.currency).minus(dec(transaction.cash_amount)));
    }
  }

  const snapshots = [];
  let totalSgd = ZERO;
  const realizedByCurrency = new Map();
  for (const [securityId, shares] of quantity) {
    if (shares.isZero()) continue;
    const security = securities[securityId];
    const close = lastCloseOnOrBefore(prices, securityId, asOf);
    const marketValue = shares.times(dec(close.close));
    const rate = rateForDate(security.currency, asOf, fxRates);
    const marketSgd = marketValue.times(rate);
    totalSgd = totalSgd.plus(marketSgd);
    const averageCost = mapDefault(costBasis, securityId).div(shares);
    snapshots.push({
      security_id: String(securityId),
      ticker: security.ticker,
      quantity: shares,
      weighted_average_cost: averageCost,
      cost_basis_native: mapDefault(costBasis, securityId),
      market_value_native: marketValue,
      market_value_sgd: marketSgd,
      unrealized_pl_native: marketValue.minus(mapDefault(costBasis, securityId)),
      realized_pl_native: mapDefault(realized, securityId),
    });
  }
  for (const [securityId, amount] of realized) {
    if (securities[securityId]) {
      const currency = securities[securityId].currency;
      const existing = realizedByCurrency.get(currency);
      realizedByCurrency.set(currency, (existing ?? ZERO).plus(amount));
    }
  }
  for (const [currency, amount] of cash) {
    totalSgd = totalSgd.plus(amount.times(rateForDate(currency, asOf, fxRates)));
  }

  snapshots.sort((a, b) => (a.ticker < b.ticker ? -1 : a.ticker > b.ticker ? 1 : 0));

  return {
    as_of: asOf,
    holdings: snapshots,
    cash_by_currency: Object.fromEntries(cash),
    realized_pl_native: Object.fromEntries(realizedByCurrency),
    total_market_value_sgd: totalSgd,
    methodology: { cost_basis: 'weighted_average', end_value: 'mark_to_market' },
  };
}
