'use strict';
// Labels are the authoritative numbering for the "play video N" command.
const LABEL_CLASS = 'treadmill-video-number';
const STORAGE_KEY = 'treadmill_numbering_enabled';
let numbered = [];
let scheduled = false;
let numberingEnabled = true;
let lastUrl = location.href;
let lastPageKey = location.pathname + location.search;

// YouTube's homepage often uses links without #thumbnail or #video-title IDs.
// Resolve each card once, and use the same resolved URL for overlays, snapshots,
// and play_video selection. Avoid Shorts, shelves, and obvious ad containers.
function watchLink(card) {
  return [...card.querySelectorAll('a[href*="/watch?v="]')].find(a => {
    try { return new URL(a.href).searchParams.has('v'); }
    catch (_) { return false; }
  }) || null;
}
function thumbnail(card) {
  return card.querySelector('a#thumbnail, ytd-thumbnail a, yt-thumbnail-view-model a, a[href*="/watch?v="]') || card;
}
// Assign one page-wide number to every loaded ordinary video, even when it is
// off-screen. Shorts shelves do not restart the sequence. Display labels only
// for videos whose thumbnails intersect the viewport.
function thumbnailRect(card) { return thumbnail(card).getBoundingClientRect(); }
function visibleThumbnail(card) {
  const rect = thumbnailRect(card);
  const w = Math.max(0, Math.min(rect.right, innerWidth) - Math.max(rect.left, 0));
  const h = Math.max(0, Math.min(rect.bottom, innerHeight) - Math.max(rect.top, 0));
  return rect.width > 0 && rect.height > 0 && w >= 8 && h >= 8;
}
function candidates() {
  const watchPage = location.pathname === '/watch';
  const playlistPage = location.pathname === '/playlist';
  const playlistWatch = watchPage && new URL(location.href).searchParams.has('list');
  const selector = playlistPage ? 'ytd-playlist-video-renderer' : playlistWatch
    ? 'ytd-playlist-panel-renderer ytd-playlist-panel-video-renderer' : watchPage
    ? '#secondary yt-lockup-view-model, #secondary ytd-compact-video-renderer'
    : 'ytd-video-renderer, ytd-rich-item-renderer, ytd-grid-video-renderer';
  const cards = [...document.querySelectorAll(selector)];
  const seen = new Set();
  return cards.filter(card => {
    if (card.closest('ytd-reel-shelf-renderer, ytd-rich-shelf-renderer, ytd-shorts, ytd-ad-slot-renderer, ytd-promoted-video-renderer, ytd-display-ad-renderer, ytd-in-feed-ad-layout-renderer')) return false;
    if (card.querySelector('ytd-ad-slot-renderer, ytd-promoted-video-renderer, ytd-display-ad-renderer, ytd-in-feed-ad-layout-renderer, [is-ad]')) return false;
    const link = watchLink(card);
    if (!link) return false;
    const rect = thumbnailRect(card);
    if (rect.width <= 0 || rect.height <= 0) return false;
    // Avoid duplicate cards for the same video when a renderer nests another.
    const id = new URL(link.href).searchParams.get('v');
    if (!id || (!(playlistPage || playlistWatch) && seen.has(id))) return false;
    seen.add(id);
    return true;
  }).sort((a, b) => {
    if (playlistPage || playlistWatch) return 0;
    const ar = thumbnailRect(a), br = thumbnailRect(b);
    // Grid thumbnails may differ a few pixels in top coordinate; group rows.
    return Math.abs(ar.top - br.top) < 24 ? ar.left - br.left : ar.top - br.top;
  });
}
// Canonical playlist registry. The same list drives labels, logging and selection.
// Do not use a card's aggregate text as its title: it includes counts and badges.
function playlistRegistry() {
  // Ignore guide/sidebar links and hidden renderers from previous SPA pages.
  const root = document.querySelector('ytd-page-manager') || document.querySelector('main');
  if (!root) return [];
  const cards = [...root.querySelectorAll('yt-lockup-view-model, ytd-grid-playlist-renderer, ytd-playlist-renderer, ytd-rich-item-renderer, ytd-compact-playlist-renderer')];
  const seen = new Set();
  const entries = [];
  const clean = value => (value || '').replace(/\s+/g, ' ').trim();
  const validTitle = value => value && !/^(?:[\d,]+\s+(?:videos?|lessons?|songs?|tracks?)|\d+|play all|view full playlist)$/i.test(value);
  for (const card of cards) {
    if (card.closest('ytd-reel-shelf-renderer, ytd-rich-shelf-renderer, ytd-ad-slot-renderer')) continue;
    const rect = card.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) continue;
    // Prefer the explicit playlist destination over its first video's watch URL.
    const links = [...card.querySelectorAll('a[href*="list="]')];
    const link = links.find(a => {try {return new URL(a.href).pathname === '/playlist';} catch {return false;}}) || links[0];
    if (!link) continue;
    let id;
    try { id = new URL(link.href).searchParams.get('list'); } catch (_) { continue; }
    if (!id || seen.has(id)) continue;
    // Dedicated heading text precedes thumbnail labels (which may name a song).
    const titleElements = [...card.querySelectorAll('[class*="metadata-view-model__title"], #playlist-title, h3, [role="heading"], #video-title')];
    const values = titleElements.flatMap(el => {
      const copy = el.cloneNode(true);
      copy.querySelectorAll('.treadmill-playlist-number, .treadmill-video-number').forEach(n => n.remove());
      return [el.getAttribute('title'), copy.textContent, el.getAttribute('aria-label')];
    });
    const title = values.map(clean).find(validTitle) || '(title unavailable)';
    seen.add(id);
    entries.push({index: entries.length + 1, id, title,
      url: 'https://www.youtube.com/playlist?list=' + encodeURIComponent(id), card});
  }
  return entries;
}
function refreshPlaylistLabels() {
  document.querySelectorAll('.treadmill-playlist-number').forEach(el => el.remove());
  if (!numberingEnabled || location.pathname !== '/feed/playlists') return;
  for (const item of playlistRegistry()) {
    const card = item.card;
    if (!card || !card.isConnected) continue;
    const label = document.createElement('span');
    label.className = 'treadmill-playlist-number';
    label.textContent = String(item.index);
    label.style.cssText = 'position:absolute!important;top:6px!important;left:6px!important;z-index:2147483647!important;background:#7b1fa2!important;color:white!important;font:bold 20px Arial!important;border:2px solid white!important;border-radius:7px!important;padding:4px 9px!important;pointer-events:none!important;';
    if (getComputedStyle(card).position === 'static') card.style.position = 'relative';
    card.appendChild(label);
  }
}
function refresh() {
  scheduled = false;
  // MutationObserver ignores our own overlay mutations to avoid refresh loops.
  document.querySelectorAll('.' + LABEL_CLASS).forEach(el => el.remove());
  const allVideos = numberingEnabled && location.pathname !== '/feed/playlists' ? candidates() : [];
  numbered = allVideos.map((card, i) => ({card, index:i + 1}))
    .filter(({card}) => visibleThumbnail(card));
  numbered.forEach(({card, index}) => {
    const thumb = thumbnail(card);
    const label = document.createElement('span');
    label.className = LABEL_CLASS;
    label.textContent = String(index);
    label.style.cssText = 'position:absolute!important;top:6px!important;left:6px!important;z-index:2147483647!important;background:#1565ff!important;color:white!important;font:bold 22px Arial!important;border:2px solid white!important;border-radius:7px!important;padding:5px 10px!important;pointer-events:none!important;box-shadow:0 1px 6px #000!important;';
    if (getComputedStyle(thumb).position === 'static') thumb.style.position = 'relative';
    thumb.appendChild(label);
  });
  refreshPlaylistLabels();
}
function schedule() { if (!scheduled) { scheduled = true; setTimeout(refresh, 200); } }
window.addEventListener('scroll', schedule, {passive:true});
window.addEventListener('resize', schedule);
window.addEventListener('yt-navigate-finish', () => {lastUrl=location.href; numbered=[]; schedule();});
new MutationObserver(mutations => {
  if (mutations.some(m => [...m.addedNodes, ...m.removedNodes].some(n =>
      n.nodeType === 1 && !n.classList?.contains(LABEL_CLASS) && !n.classList?.contains('treadmill-playlist-number') && !n.closest?.('.' + LABEL_CLASS) && !n.closest?.('.treadmill-playlist-number')))) schedule();
}).observe(document.documentElement, {childList:true, subtree:true});
// Catch SPA URL changes even when YouTube doesn't fire the usual navigation event.
setInterval(() => {if (location.href !== lastUrl) {lastUrl=location.href; numbered=[]; schedule();}}, 1000);
chrome.storage.local.get({[STORAGE_KEY]:true}, result => {
  numberingEnabled = result[STORAGE_KEY] !== false;
  schedule();
});
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'local' && changes[STORAGE_KEY]) {
    numberingEnabled = changes[STORAGE_KEY].newValue !== false;
    schedule();
  }
});
schedule();
function describeVisibleVideos() {
  refresh();
  return numbered.map(({card, index}) => {
    const r = card.getBoundingClientRect();
    const link = watchLink(card);
    const visibleHeight = Math.max(0, Math.min(r.bottom, innerHeight) - Math.max(r.top, 0));
    return {
      index,
      title: (card.querySelector('a#video-title, #video-title, h3, [title]')?.getAttribute('title') || card.querySelector('a#video-title, #video-title, h3, [title]')?.textContent || link?.getAttribute('title') || '').trim().slice(0, 200),
      url: link?.href || '',
      bounds: {top:r.top,bottom:r.bottom,left:r.left,right:r.right,width:r.width,height:r.height},
      visible_fraction: r.height > 0 ? Number((visibleHeight / r.height).toFixed(3)) : 0
    };
  });
}
function getBrowserState() {
  return {
    timestamp: new Date().toISOString(),
    url: location.href,
    title: document.title,
    viewport: {width:innerWidth,height:innerHeight,scroll_x:scrollX,scroll_y:scrollY},
    numbering_enabled: numberingEnabled,
    visible_videos: describeVisibleVideos(),
    player: (() => {
      const video = document.querySelector('video');
      return video ? {paused:video.paused,current_time:video.currentTime,duration:Number.isFinite(video.duration) ? video.duration : null,muted:video.muted,volume:video.volume} : null;
    })()
  };
}
const wakePauses = new Map();
chrome.runtime.onMessage.addListener((cmd, sender, sendResponse) => {
  if (cmd.tool === '__wake_pause') {
    if (Date.now()/1000 > cmd.expires_at) {sendResponse({ok:false,error:'wake_pause_expired'});return;}
    const video=document.querySelector('video');
    const wasPlaying=Boolean(video && !video.paused && !video.ended);
    if (wasPlaying) {
      const state={video,url:location.href,src:video.currentSrc};
      video.pause();
      state.timer=setTimeout(() => {
        if(wakePauses.get(cmd.token)!==state)return;
        wakePauses.delete(cmd.token);
        if(location.href===state.url && document.querySelector('video')===video && video.currentSrc===state.src && video.paused)
          video.play().catch(()=>{});
      },60000);
      wakePauses.set(cmd.token,state);
    }
    sendResponse({ok:true,was_playing:wasPlaying});return;
  }
  if (cmd.tool === '__wake_release') {
    const state=wakePauses.get(cmd.token);
    if(!state){sendResponse({ok:true,restored:false});return;}
    clearTimeout(state.timer);wakePauses.delete(cmd.token);
    if(cmd.restore && location.href===state.url && document.querySelector('video')===state.video && state.video.currentSrc===state.src && state.video.paused) {
      state.video.play().then(()=>sendResponse({ok:true,restored:true}))
        .catch(e=>sendResponse({ok:false,error:'playback_blocked',detail:String(e)}));return true;
    }
    sendResponse({ok:true,restored:false});return;
  }
  if (cmd.tool === '__scroll_position') {
    sendResponse({scroll_y: window.scrollY});
    return;
  }
  if (cmd.tool === '__snapshot') {
    try { sendResponse(getBrowserState()); }
    catch (e) { sendResponse({error:String(e)}); }
    return;
  }
  try {
    if (cmd.tool === 'play_video' || cmd.tool === 'play_playlist' ||
        (cmd.tool === 'media_control' && ['pause','play'].includes(cmd.action)) ||
        (cmd.tool === 'playlist_control' && ['next','previous'].includes(cmd.action))) {
      for (const state of wakePauses.values()) clearTimeout(state.timer);
    }
    if (cmd.tool === 'scroll_page') {
      window.scrollBy({top:(cmd.direction === 'up' ? -1 : 1) * innerHeight * cmd.fraction, behavior:'smooth'});
      sendResponse({ok:true, detail:'Scroll requested'});
      return;
    }
    if (cmd.tool === 'list_playlists') {
      refreshPlaylistLabels();
      const playlists = playlistRegistry().map(({index,id,title,url}) => ({index,id,title,url}));
      sendResponse({ok:true,playlists,detail:playlists.length ? 'Playlists found on current page' : 'No playlist links found here; open YouTube Playlists first'});
      return;
    }
    if (cmd.tool === 'play_playlist') {
      const entries = playlistRegistry();
      const index = Number.isInteger(cmd.index) ? cmd.index : null;
      const name = String(cmd.name || '').toLowerCase().trim();
      let matches = index !== null ? entries.filter(x => x.index === index) :
        entries.filter(x => x.title.toLowerCase() === name);
      if (index === null && name && matches.length === 0)
        matches = entries.filter(x => x.title.toLowerCase().includes(name));
      if (matches.length !== 1) {
        sendResponse({ok:false,error:matches.length ? 'ambiguous_playlist' : 'playlist_not_found_on_page',
          available:entries.map(({index,title})=>({index,title})),matches:matches.map(({index,title})=>({index,title}))});
        return;
      }
      sendResponse({ok:true,url:matches[0].url,selected:{index:matches[0].index,title:matches[0].title},
        detail:'Playlist selected'});
      return;
    }
    if (cmd.tool === '__playlist_start_url') {
      const expected = String(cmd.playlist_id || '');
      if (location.pathname !== '/playlist' || new URL(location.href).searchParams.get('list') !== expected) {
        sendResponse({ok:false,error:'playlist_page_not_ready'}); return;
      }
      // The user's DOM exposes Play all as a link in this header.
      const playAll = [...document.querySelectorAll('yt-page-header-renderer a[href*="/watch?v="], ytd-playlist-header-renderer a[href*="/watch?v="]')]
        .find(a => {try {return new URL(a.href).searchParams.get('list') === expected && a.getBoundingClientRect().width > 0;} catch {return false;}});
      const cards = [...document.querySelectorAll('ytd-playlist-video-renderer')];
      const link = playAll || cards.filter(card => card.getBoundingClientRect().width > 0).map(watchLink).find(Boolean);
      if (!link) {sendResponse({ok:false,error:'playlist_has_no_loaded_playable_videos'});return;}
      const url = new URL(link.href);
      url.searchParams.set('list', expected);
      sendResponse({ok:true,url:url.href}); return;
    }
    if (cmd.tool === '__ensure_playlist_playing') {
      const url = new URL(location.href);
      if (url.pathname !== '/watch' || url.searchParams.get('list') !== cmd.playlist_id) {
        sendResponse({ok:false,error:'playlist_watch_page_not_ready'}); return;
      }
      const video = document.querySelector('video');
      if (!video) {sendResponse({ok:false,error:'no_video_player'});return;}
      video.play().then(() => sendResponse({ok:!video.paused,playing:!video.paused}))
        .catch(error => sendResponse({ok:false,error:'playback_blocked',detail:String(error)}));
      return true;
    }
    if (cmd.tool === 'playlist_control') {
      const action = cmd.action;
      if (action === 'next' || action === 'previous') {
        const button = document.querySelector(action === 'next' ? '.ytp-next-button' : '.ytp-prev-button');
        if (!button || button.getAttribute('aria-disabled') === 'true' || button.disabled) {sendResponse({ok:false,error:'playlist_button_unavailable'});return;}
        button.click();sendResponse({ok:true,detail:action+' requested'});return;
      }
      if (action === 'shuffle') {
        const button = document.querySelector('ytd-playlist-panel-renderer button[aria-label*="Shuffle"], ytd-playlist-panel-renderer button[title*="Shuffle"], ytd-playlist-header-renderer button[aria-label*="Shuffle"], button[aria-label="Shuffle playlist"]');
        if (!button) {sendResponse({ok:false,error:'shuffle_control_not_found'});return;}
        button.click();sendResponse({ok:true,detail:'Shuffle toggle clicked; state not verified'});return;
      }
    }
    if (cmd.tool === 'play_video') {
      refresh();
      const mapping = describeVisibleVideos();
      const item = mapping.find(v => v.index === cmd.visible_index);
      if (!item) { sendResponse({ok:false, error:'video_not_found', available:mapping}); return; }
      if (!item.url) { sendResponse({ok:false, error:'missing_video_url', available:mapping}); return; }
      // Navigation to the exact mapped URL avoids clicking Shorts shelves.
      sendResponse({ok:true, detail:'Navigating to selected video', selected:item, available:mapping});
      location.assign(item.url);
      return;
    }
    const video = document.querySelector('video');
    if (!video) {sendResponse({ok:false,error:'no_video_player'});return;}
    if (cmd.tool === 'media_control') {
      if (cmd.action === 'pause') video.pause();
      else if (cmd.action === 'play') video.play().catch(() => {});
      else if (cmd.action === 'seek_forward') video.currentTime += 10;
      else if (cmd.action === 'seek_backward') video.currentTime -= 10;
      sendResponse({ok:true,detail:'Media control requested'});return;
    }
    if (cmd.tool === 'set_volume') {
      video.volume = cmd.percentage / 100;video.muted = false;
      sendResponse({ok:true,detail:'Volume set'});return;
    }
    sendResponse({ok:false,error:'unknown_tool'});
  } catch (e) {sendResponse({ok:false,error:String(e)});}
});
schedule();
