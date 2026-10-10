// The service worker only opens the controller page. It does not poll:
// Manifest V3 service workers are suspended when idle.
chrome.action.onClicked.addListener(async () => {
  const controllerUrl = chrome.runtime.getURL('controller.html');
  const tabs = await chrome.tabs.query({url: controllerUrl});
  if (tabs.length) {
    await chrome.tabs.update(tabs[0].id, {active: true});
    await chrome.windows.update(tabs[0].windowId, {focused: true});
  } else {
    await chrome.tabs.create({url: controllerUrl, active: true});
  }
});
