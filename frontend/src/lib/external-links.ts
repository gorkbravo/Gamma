export type OpenExternalUrlResult =
  | "desktop-opened"
  | "browser-opened"
  | "browser-blocked"
  | "invalid-url"
  | "open-failed";

export interface ExternalLinkDependencies {
  invokeCommand?: (command: string, args: Record<string, unknown>) => Promise<unknown>;
  openBrowserWindow?: (url: string, target: string, features: string) => Window | null;
  tauriAvailable?: boolean;
  logger?: Pick<Console, "warn">;
}

function normalizeExternalUrl(rawUrl: string) {
  try {
    const url = new URL(rawUrl, typeof window === "undefined" ? "http://localhost" : window.location.href);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return null;
    }
    return url.toString();
  } catch {
    return null;
  }
}

async function resolveTauriInvoke(dependencies: ExternalLinkDependencies) {
  if (dependencies.invokeCommand) {
    return dependencies.invokeCommand;
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke;
}

export async function openExternalUrl(
  rawUrl: string,
  dependencies: ExternalLinkDependencies = {}
): Promise<OpenExternalUrlResult> {
  const url = normalizeExternalUrl(rawUrl);
  if (!url) {
    return "invalid-url";
  }

  const tauriAvailable =
    dependencies.tauriAvailable ??
    (typeof window !== "undefined" && window.__TAURI_INTERNALS__ != null);

  if (tauriAvailable) {
    try {
      const invoke = await resolveTauriInvoke(dependencies);
      await invoke("open_external_url", { url });
      return "desktop-opened";
    } catch (error) {
      dependencies.logger?.warn?.("Unable to open external URL through the desktop shell.", error);
    }
  }

  const openBrowserWindow =
    dependencies.openBrowserWindow ??
    (typeof window !== "undefined" ? window.open.bind(window) : () => null);
  const openedWindow = openBrowserWindow(url, "_blank", "noopener,noreferrer");
  if (!openedWindow) {
    return tauriAvailable ? "open-failed" : "browser-blocked";
  }
  return "browser-opened";
}

function shouldHandleExternalAnchor(anchor: HTMLAnchorElement) {
  const url = normalizeExternalUrl(anchor.href);
  if (!url) {
    return false;
  }
  if (typeof window === "undefined") {
    return true;
  }
  return new URL(url).origin !== window.location.origin || anchor.target === "_blank";
}

export function installExternalLinkHandler(
  root: Document | HTMLElement = document,
  dependencies: ExternalLinkDependencies = {}
) {
  const handleClick = (event: Event) => {
    if (!(event instanceof MouseEvent)) {
      return;
    }
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    ) {
      return;
    }
    const target = event.target;
    if (!(target instanceof Element)) {
      return;
    }
    const anchor = target.closest<HTMLAnchorElement>("a[href]");
    if (!anchor || anchor.hasAttribute("download") || !shouldHandleExternalAnchor(anchor)) {
      return;
    }

    event.preventDefault();
    void openExternalUrl(anchor.href, dependencies);
  };

  root.addEventListener("click", handleClick);
  return () => root.removeEventListener("click", handleClick);
}
