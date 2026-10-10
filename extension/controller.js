'use strict';

const SERVER = 'http://127.0.0.1:8765';
const status = document.getElementById('status');
const history = document.getElementById('history');
let running = true;
const numberingCheckbox = document.getElementById('numbering');
chrome.storage.local.get({treadmill_numbering_enabled:true}, settings => {
  numberingCheckbox.checked = settings.treadmill_numbering_enabled !== false;
});
numberingCheckbox.addEventListener('change', () => {
  chrome.storage.local.set({treadmill_numbering_enabled:numberingCheckbox.checked});
});

function log(message) {
  history.textContent = `${new Date().toLocaleTimeString()} ${message}\n` + history.textContent.slice(0, 3000);
}

function isYoutube(tab) {
  return Boolean(tab.url && /^https:\/\/www\.youtube\.com\//.test(tab.url));
}

async function chooseTargetTab() {
  // Prefer the currently selected YouTube tab, otherwise a recently accessed one.
  const tabs = await chrome.tabs.query({});
  const youtubeTabs = tabs.filter(isYoutube);
  youtubeTabs.sort((a, b) => (b.lastAccessed || 0) - (a.lastAccessed || 0));
  return youtubeTabs.find(t => t.active) || youtubeTabs[0] || null;
}

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function contentState(tabId, timeoutMs = 9000) {
  const deadline = Date.now() + timeoutMs;
  let lastError = 'content_script_unavailable';
  while (Date.now() < deadline) {
    try {
      const state = await chrome.tabs.sendMessage(tabId, {tool:'__snapshot'});
      if (state && !state.error) return {ok:true, state};
      lastError = state?.error || 'empty_snapshot';
    } catch (error) { lastError = String(error); }
    await sleep(300);
  }
  return {ok:false,error:'content_script_unavailable',detail:lastError};
}

async function snapshot() {
  const tab = await chooseTargetTab();
  if (!tab?.id) return {ok:false, error:'no_youtube_tab'};
  const stateResult = await contentState(tab.id);
  if (!stateResult.ok) return {...stateResult,tab_url:tab.url};
  const result = {ok:true,tab_id:tab.id,tab_url:tab.url,state:stateResult.state};
  if (!tab.active) {
    result.screenshot_error = 'youtube_tab_not_active';
  } else {
    try {
      const image = await chrome.tabs.captureVisibleTab(tab.windowId, {format:'png'});
      if (image?.startsWith('data:image/png;base64,')) result.screenshot_data_url = image;
      else result.screenshot_error = 'unexpected_capture_format';
    } catch (error) { result.screenshot_error = String(error); }
  }
  return result;
}

async function waitForScrollToSettle(tabId, timeoutMs = 2500) {
  let previous = null;
  let stable = 0;
  const deadline = Date.now() + timeoutMs;
  await sleep(180);
  while (Date.now() < deadline) {
    try {
      const response = await chrome.tabs.sendMessage(tabId, {tool:'__scroll_position'});
      const y = response?.scroll_y;
      if (typeof y === 'number') {
        stable = previous !== null && Math.abs(y - previous) < 1 ? stable + 1 : 0;
        previous = y;
        if (stable >= 3) return {settled:true,scroll_y:y};
      }
    } catch (error) { return {settled:false,error:String(error)}; }
    await sleep(120);
  }
  return {settled:false,scroll_y:previous,reason:'scroll_settle_timeout'};
}

async function execute(command) {
  if (command.tool === '__snapshot') return snapshot();
  if (['show_playlists', 'open_playlists', 'list_playlists'].includes(command.tool)) {
    const url = 'https://www.youtube.com/feed/playlists';
    const tab = await chooseTargetTab();
    const destination = tab ? (tab.url?.startsWith(url) ? tab : await chrome.tabs.update(tab.id, {url})) : await chrome.tabs.create({url,active:true});
    const ready = await contentState(destination.id, 12000);
    if (!ready.ok) return {ok:false,error:'playlist_page_not_ready',url,detail:ready.detail};
    // YouTube can render the library asynchronously after content script injection.
    let result = {ok:true,playlists:[]};
    let signature = '';
    let stableSince = Date.now();
    const started = Date.now();
    let settled = false;
    for (let attempt = 0; attempt < 12; attempt++) {
      try { result = await chrome.tabs.sendMessage(destination.id, {tool:'list_playlists'}); }
      catch (error) { result = {ok:false,error:String(error)}; }
      const current = JSON.stringify(result?.playlists || []);
      if (current !== signature) { signature = current; stableSince = Date.now(); }
      if (result?.ok && result.playlists?.length && Date.now() - started >= 2000 && Date.now() - stableSince >= 1500) { settled = true; break; }
      await sleep(500);
    }
    return {...result,url,tab_id:destination.id,settled,detail:result?.playlists?.length ? `Found ${result.playlists.length} loaded playlists${settled ? '' : ' (page still changing; ask to list again)'}` : 'Playlist library opened, but no playlist names were extracted'};
  }
  if (command.tool === 'play_playlist') {
    const tab = await chooseTargetTab();
    if (!tab?.id) return {ok:false,error:'no_youtube_tab'};
    const page = await contentState(tab.id, 9000);
    if (!page.ok) return {ok:false,error:'playlist_page_not_ready',detail:page.detail};
    let result;
    try { result = await chrome.tabs.sendMessage(tab.id, {tool:'play_playlist',index:command.index,name:command.name}); }
    catch (error) { return {ok:false,error:'playlist_selection_unavailable',detail:String(error)}; }
    if (!result?.ok) return result || {ok:false,error:'empty_playlist_selection_response'};
    const playlistId = new URL(result.url).searchParams.get('list');
    await chrome.tabs.update(tab.id, {url:result.url});
    let start;
    for (let attempt = 0; attempt < 16; attempt++) {
      try { start = await chrome.tabs.sendMessage(tab.id, {tool:'__playlist_start_url',playlist_id:playlistId}); } catch (_) {}
      if (start?.ok) break;
      await sleep(250);
    }
    if (!start?.ok) return {...result,ok:false,error:'playlist_playback_unavailable',detail:start?.error || 'Playlist songs did not load'};
    await chrome.tabs.update(tab.id, {url:start.url});
    let playback;
    for (let attempt = 0; attempt < 16; attempt++) {
      try { playback = await chrome.tabs.sendMessage(tab.id, {tool:'__ensure_playlist_playing',playlist_id:playlistId}); } catch (_) {}
      if (playback?.ok || playback?.error === 'playback_blocked') break;
      await sleep(250);
    }
    return {...result,url:start.url,ok:Boolean(playback?.ok),playback,
      error:playback?.ok ? undefined : (playback?.error || 'playback_not_verified'),
      detail:playback?.ok ? 'Selected playlist is playing' : 'Playlist opened; playback could not be started'};
  }
  if (command.tool === 'youtube_search') {
    const url = 'https://www.youtube.com/results?search_query=' + encodeURIComponent(command.query);
    const tab = await chooseTargetTab();
    const destination = tab ? await chrome.tabs.update(tab.id, {url}) : await chrome.tabs.create({url, active:true});
    return {ok:true, detail:'YouTube search navigation requested', url, tab_id:destination.id};
  }
  const tab = await chooseTargetTab();
  if (!tab?.id) return {ok:false,error:'no_youtube_tab'};
  try {
    const result = await chrome.tabs.sendMessage(tab.id, command);
    if (!result) return {ok:false,error:'empty_content_script_response'};
    if (result.ok && command.tool === 'scroll_page') {
      result.scroll_settle = await waitForScrollToSettle(tab.id);
    }
    return result;
  } catch (e) {
    return {ok:false,error:'content_script_unavailable', detail:String(e)};
  }
}

async function report(command, result) {
  try {
    await fetch(`${SERVER}/result`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({request_id:command.request_id, result})
    });
  } catch (e) { log('Could not report result: ' + e.message); }
}

async function pollForever() {
  while (running) {
    try {
      // Long polling: Flask waits for a command, avoiding a busy 1-second timer.
      const response = await fetch(`${SERVER}/next?wait=20`, {cache: 'no-store'});
      if (!response.ok) throw new Error(`Server returned HTTP ${response.status}`);
      status.textContent = 'Connected to local assistant';
      const command = await response.json();
      if (command.tool) {
        try {
          const result = await execute(command);
          log(`${result.ok ? 'Executed' : 'Failed'}: ${JSON.stringify({command,result})}`);
          await report(command, result);
        } catch (error) {
          const result = {ok:false,error:'extension_exception',detail:String(error)};
          log(`Command failed: ${error.message}`);
          await report(command, result);
        }
      }
    } catch (error) {
      status.textContent = 'Disconnected — retrying (is assistant.py running?)';
      await new Promise(resolve => setTimeout(resolve, 1500));
    }
  }
}

window.addEventListener('pagehide', () => { running = false; });
pollForever();
