const fs = require('fs'), vm = require('vm'), assert = require('assert');
const nodes = {};
const handlers = {};
const defaults = {query:'', company:'', minimum:'0', eligibility:'active', availability:'open', applied:'all', country:'us'};
const get = id => nodes[id] ||= {value:defaults[id]||'', innerHTML:'', textContent:'', addEventListener(type, fn){handlers[id+':'+type]=fn}, classList:{add(){}}};
const context = vm.createContext({document:{getElementById:get},URL,console});
let script = fs.readFileSync('dashboard/index.html','utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
script = script.replace('refresh();setInterval(refresh,60000);','');
vm.runInContext(script, context);
vm.runInContext(`data={companies:[],jobs:[
{id:'1',title:'Apple verified',company:'Apple',country_scope:'us',availability:{status:'open'}},
{id:'2',title:'Apple uncertain',company:'Apple',country_scope:'us',availability:{status:'unverified'}},
{id:'3',title:'Google verified',company:'Google',country_scope:'us',availability:{status:'open'}},
{id:'4',title:'Unknown location',company:'Apple',country_scope:'unknown',availability:{status:'open'}}]};render()`,context);
assert(get('jobs').innerHTML.includes('Apple verified'));
assert(!get('jobs').innerHTML.includes('Apple uncertain'));
assert(!get('jobs').innerHTML.includes('Unknown location'));
get('company').value='Apple'; vm.runInContext('render()',context);
assert(!get('jobs').innerHTML.includes('Google verified'));
get('availability').value='active'; vm.runInContext('render()',context);
assert(get('jobs').innerHTML.includes('Apple uncertain'));
get('country').value='unknown';vm.runInContext('render()',context);
assert(get('jobs').innerHTML.includes('Unknown location'));
assert(!get('jobs').innerHTML.includes('Apple verified'));
console.log('Dashboard company, availability and US location filters passed');

get('company').value='Google';
vm.runInContext(`data.companies=[{company:'Google',status:'ok',jobs_found:1,notes:[],coverage:{complete:true,pages_checked:2,pages_total:2,listings_seen:4,reported_total:4,unique_listings:3,scope:'US keyword searches',queries:[{query:'PhD <test>',listings_seen:4,reported_total:4,pages_checked:2,pages_total:2,complete:true}]}}];render()`,context);
assert(get('sources').innerHTML.includes('Keyword coverage'));
assert(get('sources').innerHTML.includes('3 distinct postings'));
assert(get('sources').innerHTML.includes('PhD &lt;test&gt;'));
console.log('Per-keyword coverage rendering passed');

(async()=>{
 vm.runInContext(`data.jobs=[{id:'reach-test',company:'Google',title:'Scientist',country_scope:'us',applied:true,over_my_reach:false,availability:{status:'open'}}];data.csrf_token='test';data.reach_feedback_file='over_my_reach.json';`,context);
 const box={dataset:{id:'reach-test'},checked:true,disabled:false,classList:{contains:c=>c==='reach-box'}};
 context.fetch=async(url,opts)=>{
   assert.equal(url,'/api/over-my-reach');
   assert.deepEqual(JSON.parse(opts.body),{id:'reach-test',over_my_reach:true});
   assert.equal(opts.headers['X-CSRF-Token'],'test');
   return {ok:true,json:async()=>({id:'reach-test',over_my_reach:true})};
 };
 await handlers['jobs:change']({target:box});
 assert(vm.runInContext('data.jobs[0].over_my_reach && data.jobs[0].applied',context));
 box.checked=false;
 context.fetch=async()=>({ok:false,json:async()=>({error:'disk full'})});
 await handlers['jobs:change']({target:box});
 assert.equal(box.checked,true);
 assert(get('reach-notice').textContent.includes('Not saved: disk full'));
 assert.equal(box.disabled,false);
 console.log('Reach checkbox save, independent state and rollback passed');
})().catch(error=>{console.error(error);process.exitCode=1});
