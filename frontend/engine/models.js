export const SGD = 'SGD';

export const AssetType = {
  EQUITY: 'equity',
  ETF: 'ETF',
  INDEX: 'index',
  REIT: 'REIT',
  TRUST: 'trust',
  OTHER: 'other',
};

export const DistributionPolicy = {
  ACCUMULATING: 'accumulating',
  DISTRIBUTING: 'distributing',
  NON_DISTRIBUTING: 'non_distributing',
  UNKNOWN: 'unknown',
};

export const DividendType = {
  REGULAR: 'regular',
  SPECIAL: 'special',
  RETURN_OF_CAPITAL: 'return_of_capital',
  UNKNOWN: 'unknown',
  LEGACY_ORDINARY: 'ordinary',
};

export const DIVIDEND_TYPES = new Set(Object.values(DividendType));

export const CorporateActionType = {
  SPLIT: 'split',
  REVERSE_SPLIT: 'reverse_split',
  BONUS_ISSUE: 'bonus_issue',
};

export const TransactionType = {
  BUY: 'BUY',
  SELL: 'SELL',
  DIVIDEND: 'DIVIDEND',
  CASH_DEPOSIT: 'CASH_DEPOSIT',
  CASH_WITHDRAWAL: 'CASH_WITHDRAWAL',
};

export const DataQualityStatus = {
  OK: 'OK',
  WARNING: 'WARNING',
  INCOMPLETE: 'INCOMPLETE',
  FAILED: 'FAILED',
};

export const DATE_MAX = '9999-12-31';

export const DEFAULT_SCENARIO = {
  dividends_enabled: true,
  reinvest_dividends: true,
  withholding_tax_enabled: true,
  purchase_date_rule: 'next_trading_day',
  valuation_date_rule: 'previous_trading_day',
  methodology_version: '1.0',
};

export function normalizeScenario(scenario) {
  return { ...DEFAULT_SCENARIO, ...(scenario ?? {}) };
}

export class AnalysisDataError extends Error {
  constructor(message) {
    super(message);
    this.name = 'AnalysisDataError';
  }
}

export class EngineValueError extends Error {
  constructor(message) {
    super(message);
    this.name = 'EngineValueError';
  }
}
