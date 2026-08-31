import { dec } from './money.js';

export function groupByEffectiveDate(actions) {
  const byDate = new Map();
  for (const action of actions) {
    const list = byDate.get(action.effective_date);
    if (list) list.push(action);
    else byDate.set(action.effective_date, [action]);
  }
  return byDate;
}

export function applyActions(shares, actions) {
  let adjusted = shares;
  for (const action of actions) {
    adjusted = adjusted.times(dec(action.ratio));
  }
  return adjusted;
}
