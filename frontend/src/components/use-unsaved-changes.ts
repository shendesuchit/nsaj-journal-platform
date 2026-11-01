"use client";

import { useEffect } from "react";

// A single guard covers multiple dirty forms without showing duplicate prompts.
const owners = new Map<symbol, boolean>();
let historyMarker: string | null = null;
let guardedUrl = "";
let guardedState: unknown;
let allowNavigation = false;
let restoringEntry = false;
let attached = false;
const markerKey = "__nsajUnsavedEntry";
const question = "You have unsaved changes. Leave this page and discard them?";

function unload(event: BeforeUnloadEvent) {
  if (owners.size && !allowNavigation) { event.preventDefault(); event.returnValue = ""; }
}
function click(event: MouseEvent) {
  if (!owners.size || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  const link = event.target instanceof Element ? event.target.closest<HTMLAnchorElement>("a[href]") : null;
  if (!link || (link.target && link.target !== "_self") || link.hasAttribute("download")) return;
  const destination = new URL(link.href, location.href);
  if (!["http:", "https:"].includes(destination.protocol)) return;
  if (destination.origin === location.origin && destination.pathname === location.pathname && destination.search === location.search) return;
  if (!window.confirm(question)) { event.preventDefault(); event.stopPropagation(); }
  else allowNavigation = true;
}
function pop(event: PopStateEvent) {
  if (restoringEntry) { restoringEntry = false; return; }
  if (!historyMarker || allowNavigation || ![...owners.values()].some(Boolean)) return;
  if (event.state?.[markerKey] === historyMarker) return;
  // The extra entry keeps Back on the current route until the user decides.
  // This avoids restoring a different Next route before a cancellation completes.
  if (window.confirm(question)) {
    allowNavigation = true;
    if (location.href === guardedUrl) {
      event.stopImmediatePropagation(); window.history.back();
    }
  } else {
    event.stopImmediatePropagation();
    if (location.href === guardedUrl) { restoringEntry = true; window.history.forward(); }
    else window.history.pushState({ ...(guardedState as object), [markerKey]: historyMarker }, "", guardedUrl);
  }
}
function synchronize() {
  if (owners.size && !attached) {
    window.addEventListener("beforeunload", unload);
    document.addEventListener("click", click, true);
    window.addEventListener("popstate", pop, true);
    attached = true; allowNavigation = false;
  }
  if (owners.size && [...owners.values()].some(Boolean) && !historyMarker && !allowNavigation) {
    guardedUrl = location.href; guardedState = window.history.state;
    // This is a history marker, not an authentication token. getRandomValues also works on local HTTP previews.
    historyMarker = typeof crypto.randomUUID === "function" ? crypto.randomUUID()
      : Array.from(crypto.getRandomValues(new Uint32Array(4)), value => value.toString(16).padStart(8, "0")).join("");
    window.history.pushState({ ...window.history.state, [markerKey]: historyMarker }, "", guardedUrl);
  }
  if (!owners.size && attached) {
    const marker = historyMarker;
    historyMarker = null;
    if (marker && window.history.state?.[markerKey] === marker && location.href === guardedUrl) window.history.back();
    window.removeEventListener("beforeunload", unload);
    document.removeEventListener("click", click, true);
    window.removeEventListener("popstate", pop, true);
    attached = false; allowNavigation = false; restoringEntry = false;
  }
}

/** Guards links, unload, and history traversal without saving private form values. */
export function confirmDiscardUnsavedChanges(): boolean {
  return !owners.size || window.confirm(question);
}

export function useUnsavedChanges(dirty: boolean, { history = true }: { history?: boolean } = {}) {
  useEffect(() => {
    if (!dirty) return;
    const owner = Symbol("unsaved form");
    owners.set(owner, history); synchronize();
    return () => { owners.delete(owner); synchronize(); };
  }, [dirty, history]);
}
