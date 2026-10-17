import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {dcaAnalysis} from './dca.js';
import {createRequest} from './protocol.js';
import {createEngineHost, validateRequestPayload} from './worker.js';
const cases=JSON.parse(readFileSync(new URL('../../tests/fixtures/redesign/sprint-11-dca.json',import.meta.url))).fixtures;
const python=JSON.parse(readFileSync(new URL('../../tests/fixtures/redesign/sprint-11-python-results.json',import.meta.url)));
function compare(a,b){if(Array.isArray(b)){assert.equal(a.length,b.length);b.forEach((v,i)=>compare(a[i],v));}else if(b&&typeof b==='object'){assert.deepEqual(Object.keys(a).sort(),Object.keys(b).sort());Object.keys(b).forEach(k=>compare(a[k],b[k]));}else if(b!==null && typeof b!=='boolean' && /^-?\d+(\.\d+)?([eE][+-]?\d+)?$/.test(String(b))){assert(Math.abs(Number(a)-Number(b))<1e-9);}else assert.deepEqual(a,b);}
for(const test of cases){
 const p=test.input;
 const result=dcaAnalysis({security:p.security,prices:p.prices,fxRates:p.fx_rates,startDate:p.start_date,endDate:p.end_date,initialSgd:p.initial_sgd,contributionSgd:p.contribution_sgd,frequency:p.frequency,scenario:p.scenario,dividends:p.dividends});
 for(const [field,expected] of Object.entries(test.expected)){
  if(field==='recurring_count') assert.equal(result.contribution_dates.length,expected);
  else assert(Math.abs(Number(result[field])-Number(expected))<1e-9,`${test.name}: ${field}`);
 }
 if(test.name==='fx-initial-and-recurring')assert(Math.abs(Number(result.xirr)-(0.5**(365.2425/31)-1))<1e-9);
 compare(JSON.parse(JSON.stringify(result)),python[test.name]);
 const message=await new Promise((resolve,reject)=>{
  const host=createEngineHost({post:msg=>{if(msg.type==='result')resolve(msg);}});
  host.handleMessage(createRequest('dca',p));
  setTimeout(()=>reject(Error('worker timeout')),10000).unref();
 });
 assert.equal(message.ok,true,JSON.stringify(message));
 for(const [field,expected]of Object.entries(test.expected))if(field!=='recurring_count')assert(Math.abs(Number(message.result[field])-Number(expected))<1e-9);
 console.log(`PASS: ${test.name} direct engine + worker request adapter`);
}
assert(validateRequestPayload('dca',{...cases[0].input,initial_sgd:100}).some(p=>p.includes('must be a string')));
for(const initial of ['-1','NaN','Infinity'])assert.throws(()=>dcaAnalysis({security:cases[0].input.security,prices:cases[0].input.prices,fxRates:[],startDate:'2024-01-01',endDate:'2024-12-02',initialSgd:initial,contributionSgd:'500'}),/finite and non-negative/);
console.log('PASS: invalid initial amounts and numeric worker payload rejected.');
