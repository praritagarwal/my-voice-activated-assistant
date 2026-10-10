'use strict';
const SERVER='http://127.0.0.1:8765';
const CONTROLLER=chrome.runtime.getURL('controller.html');
let opening=null;

async function ensureController(focus=false) {
  if(opening)return opening;
  opening=(async()=>{
    const tabs=await chrome.tabs.query({url:CONTROLLER});
    if(tabs.length){
      await chrome.tabs.update(tabs[0].id,{autoDiscardable:false});
      if(focus){await chrome.tabs.update(tabs[0].id,{active:true});await chrome.windows.update(tabs[0].windowId,{focused:true});}
      return;
    }
    const tab=await chrome.tabs.create({url:CONTROLLER,active:focus});
    await chrome.tabs.update(tab.id,{autoDiscardable:false});
  })();
  try{await opening;}finally{opening=null;}
}

async function checkAssistant() {
  try {
    const response=await fetch(`${SERVER}/health`,{cache:'no-store',signal:AbortSignal.timeout(2000)});
    if(!response.ok)return;
    const health=await response.json();
    if(health.service==='treadmill-assistant' && health.protocol===2)await ensureController();
  }catch(_){} // Assistant may not be running yet.
}

async function initialise() {
  await chrome.alarms.create('assistant-connection',{periodInMinutes:0.5});
  await checkAssistant();
}
chrome.action.onClicked.addListener(()=>ensureController(true));
chrome.runtime.onInstalled.addListener(initialise);
chrome.runtime.onStartup.addListener(initialise);
chrome.alarms.onAlarm.addListener(alarm=>{if(alarm.name==='assistant-connection')checkAssistant();});
chrome.tabs.onRemoved.addListener(()=>checkAssistant());
initialise();
