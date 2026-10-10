const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('extension/background.js','utf8');
async function scenario(online,existing){
 const events={},tabs=existing ? [{id:1,windowId:1}] : [],created=[],updates=[];
 const listener=name=>({addListener(fn){events[name]=fn}});
 const context={AbortSignal,fetch:async()=>({ok:online,json:async()=>({service:'treadmill-assistant',protocol:2})}),
  chrome:{runtime:{getURL:()=> 'chrome-extension://test/controller.html',onInstalled:listener('install'),onStartup:listener('startup')},
   tabs:{query:async()=>tabs,create:async options=>{created.push(options);const tab={id:2,windowId:1};tabs.push(tab);return tab},update:async(id,options)=>updates.push(options),onRemoved:listener('remove')},
   windows:{update:async()=>{}},action:{onClicked:listener('click')},alarms:{create:async()=>{},onAlarm:listener('alarm')}}};
 vm.runInNewContext(source,context);
 await new Promise(setImmediate);await new Promise(setImmediate);
 await Promise.all([events.startup(),events.install(),events.remove()]);
 await new Promise(setImmediate);
 return {created,updates};
}
(async()=>{
 let r=await scenario(true,false);assert.equal(r.created.length,1);assert.equal(r.created[0].active,false);assert(r.updates.some(x=>x.autoDiscardable===false));
 r=await scenario(true,true);assert.equal(r.created.length,0);
 r=await scenario(false,false);assert.equal(r.created.length,0);
 console.log('3 automatic Controller startup scenarios passed');
})().catch(e=>{console.error(e);process.exitCode=1});
