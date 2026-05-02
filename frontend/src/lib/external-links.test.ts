import { describe, expect, it, vi } from "vitest";
import { openExternalUrl } from "./external-links";

describe("openExternalUrl", () => {
  it("opens http links through the desktop shell when Tauri is available", async () => {
    const invokeCommand = vi.fn().mockResolvedValue(undefined);

    const result = await openExternalUrl("https://example.com/research", {
      tauriAvailable: true,
      invokeCommand,
      openBrowserWindow: vi.fn(),
    });

    expect(result).toBe("desktop-opened");
    expect(invokeCommand).toHaveBeenCalledWith("open_external_url", {
      url: "https://example.com/research",
    });
  });

  it("falls back to browser opening outside the desktop shell", async () => {
    const openBrowserWindow = vi.fn().mockReturnValue({} as Window);

    const result = await openExternalUrl("https://example.com/news", {
      tauriAvailable: false,
      openBrowserWindow,
    });

    expect(result).toBe("browser-opened");
    expect(openBrowserWindow).toHaveBeenCalledWith(
      "https://example.com/news",
      "_blank",
      "noopener,noreferrer"
    );
  });

  it("rejects non-web schemes", async () => {
    const invokeCommand = vi.fn();
    const openBrowserWindow = vi.fn();

    const result = await openExternalUrl("javascript:alert(1)", {
      tauriAvailable: true,
      invokeCommand,
      openBrowserWindow,
    });

    expect(result).toBe("invalid-url");
    expect(invokeCommand).not.toHaveBeenCalled();
    expect(openBrowserWindow).not.toHaveBeenCalled();
  });
});
