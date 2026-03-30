const KEY_BINDINGS_WINDOW_LABEL = "keybindings";
const KEY_BINDINGS_WINDOW_TITLE = "Gamma Key Bindings";
const KEY_BINDINGS_WINDOW_URL = "keybindings.html";

export type KeyBindingsWindowOpenResult =
  | "desktop-created"
  | "desktop-focused"
  | "browser-opened"
  | "browser-blocked";

export interface WindowController {
  show(): Promise<void> | void;
  setFocus(): Promise<void> | void;
}

export interface DesktopWindowApi {
  getByLabel(label: string): Promise<WindowController | null>;
  create(label: string, options: {
    url: string;
    title: string;
    width: number;
    height: number;
    resizable: boolean;
    center: boolean;
  }): Promise<WindowController>;
}

export interface OpenKeyBindingsWindowDependencies {
  desktopApi?: DesktopWindowApi | null;
  openBrowserWindow?: (url: string, target: string, features: string) => Window | null;
}

function resolveBrowserUrl() {
  if (typeof window === "undefined") {
    return KEY_BINDINGS_WINDOW_URL;
  }
  return new URL(`/${KEY_BINDINGS_WINDOW_URL}`, window.location.href).toString();
}

async function createDesktopWindowApi(): Promise<DesktopWindowApi | null> {
  if (typeof window === "undefined" || window.__TAURI_INTERNALS__ == null) {
    return null;
  }

  const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");

  return {
    getByLabel(label: string) {
      return WebviewWindow.getByLabel(label);
    },
    create(label, options) {
      return new Promise((resolve, reject) => {
        const keybindingsWindow = new WebviewWindow(label, options);
        void keybindingsWindow.once("tauri://created", () => resolve(keybindingsWindow));
        void keybindingsWindow.once("tauri://error", (event) => {
          const detail = typeof event.payload === "string" ? event.payload : "Failed to create the key bindings window.";
          reject(new Error(detail));
        });
      });
    },
  };
}

export async function openKeyBindingsWindow(
  dependencies: OpenKeyBindingsWindowDependencies = {}
): Promise<KeyBindingsWindowOpenResult> {
  const desktopApi = dependencies.desktopApi === undefined ? await createDesktopWindowApi() : dependencies.desktopApi;

  if (desktopApi) {
    const existingWindow = await desktopApi.getByLabel(KEY_BINDINGS_WINDOW_LABEL);
    if (existingWindow) {
      await existingWindow.show();
      await existingWindow.setFocus();
      return "desktop-focused";
    }

    const createdWindow = await desktopApi.create(KEY_BINDINGS_WINDOW_LABEL, {
      url: KEY_BINDINGS_WINDOW_URL,
      title: KEY_BINDINGS_WINDOW_TITLE,
      width: 920,
      height: 760,
      resizable: true,
      center: true,
    });
    await createdWindow.show();
    await createdWindow.setFocus();
    return "desktop-created";
  }

  const browserWindowOpener =
    dependencies.openBrowserWindow ?? (typeof window !== "undefined" ? window.open.bind(window) : () => null);

  const popup = browserWindowOpener(
    resolveBrowserUrl(),
    KEY_BINDINGS_WINDOW_LABEL,
    "popup=yes,width=920,height=760,resizable=yes"
  );

  if (!popup) {
    return "browser-blocked";
  }

  popup.focus?.();
  return "browser-opened";
}
