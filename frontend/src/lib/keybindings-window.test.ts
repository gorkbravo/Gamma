import { describe, expect, it, vi } from "vitest";
import { openKeyBindingsWindow } from "./keybindings-window";

describe("openKeyBindingsWindow", () => {
  it("focuses an existing desktop window instead of creating a duplicate", async () => {
    const show = vi.fn().mockResolvedValue(undefined);
    const setFocus = vi.fn().mockResolvedValue(undefined);
    const desktopApi = {
      getByLabel: vi.fn().mockResolvedValue({ show, setFocus }),
      create: vi.fn(),
    };

    const result = await openKeyBindingsWindow({
      desktopApi,
      openBrowserWindow: vi.fn(),
    });

    expect(result).toBe("desktop-focused");
    expect(desktopApi.getByLabel).toHaveBeenCalledWith("keybindings");
    expect(desktopApi.create).not.toHaveBeenCalled();
    expect(show).toHaveBeenCalled();
    expect(setFocus).toHaveBeenCalled();
  });

  it("falls back to opening a popup in the browser build", async () => {
    const focus = vi.fn();
    const openBrowserWindow = vi.fn().mockReturnValue({ focus });

    const result = await openKeyBindingsWindow({
      desktopApi: null,
      openBrowserWindow,
    });

    expect(result).toBe("browser-opened");
    expect(openBrowserWindow).toHaveBeenCalled();
    expect(focus).toHaveBeenCalled();
  });
});
