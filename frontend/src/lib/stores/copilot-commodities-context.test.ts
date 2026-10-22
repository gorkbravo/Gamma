import { describe, expect, it } from "vitest";
import type { CommodityWorkspaceResponse } from "../api/types";
import { commoditiesWorkspace, getViewedCommodityInstrumentIds } from "./app";

// GUA-20261021-6: el contexto de Commodities debe recordar cada instrumento visto en la sesión,
// no solo el seleccionado, para que Copilot pueda detallar también la curva de Brent.
describe("viewed commodity instruments", () => {
  it("records each selected instrument once, most recent first, as identities only", () => {
    const workspace = (instrumentId: string) =>
      ({ selected_instrument_id: instrumentId }) as unknown as CommodityWorkspaceResponse;
    commoditiesWorkspace.set(workspace("wti"));
    commoditiesWorkspace.set(workspace("brent"));
    commoditiesWorkspace.set(workspace("wti"));
    commoditiesWorkspace.set(null);
    expect(getViewedCommodityInstrumentIds().slice(0, 2)).toEqual(["wti", "brent"]);
    for (const id of ["gold", "silver", "copper", "henry_hub", "gasoline"]) {
      commoditiesWorkspace.set(workspace(id));
    }
    expect(getViewedCommodityInstrumentIds()).toHaveLength(6);
    expect(getViewedCommodityInstrumentIds()[0]).toBe("gasoline");
  });
});
