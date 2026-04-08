const THEME_COLOR_TOKENS = new Map<string, string>([
  ["#7aa6c8", "--chart-primary"],
  ["#c49a5a", "--chart-secondary"],
  ["#b65d54", "--chart-negative"],
  ["#d1645d", "--chart-negative"]
]);

export interface ColorTokenReader {
  getPropertyValue(name: string): string;
}

export function resolveChartColor(rawColor: string, tokens: ColorTokenReader) {
  const trimmed = rawColor.trim();
  const variableMatch = trimmed.match(/^var\((--[^),\s]+)/i);
  if (variableMatch) {
    const resolved = tokens.getPropertyValue(variableMatch[1]).trim();
    return resolved || trimmed;
  }
  const themeToken = THEME_COLOR_TOKENS.get(trimmed.toLowerCase());
  if (themeToken) {
    const resolved = tokens.getPropertyValue(themeToken).trim();
    return resolved || trimmed;
  }
  return trimmed;
}

function clampAlpha(alpha: number) {
  return Math.min(Math.max(alpha, 0), 1);
}

function rgbaString(red: number, green: number, blue: number, alpha: number) {
  return `rgba(${red}, ${green}, ${blue}, ${clampAlpha(alpha)})`;
}

export function colorWithAlpha(color: string, alpha: number) {
  const trimmed = color.trim();
  const normalizedAlpha = clampAlpha(alpha);

  const hexMatch = trimmed.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (hexMatch) {
    const hex = hexMatch[1];
    const expanded = hex.length === 3
      ? hex.split("").map((char) => `${char}${char}`).join("")
      : hex;
    const red = Number.parseInt(expanded.slice(0, 2), 16);
    const green = Number.parseInt(expanded.slice(2, 4), 16);
    const blue = Number.parseInt(expanded.slice(4, 6), 16);
    return rgbaString(red, green, blue, normalizedAlpha);
  }

  const rgbMatch = trimmed.match(/^rgba?\(([^)]+)\)$/i);
  if (rgbMatch) {
    const parts = rgbMatch[1]
      .split(",")
      .slice(0, 3)
      .map((part) => Number.parseFloat(part.trim()))
      .filter((value) => Number.isFinite(value));
    if (parts.length === 3) {
      return rgbaString(parts[0], parts[1], parts[2], normalizedAlpha);
    }
  }

  return trimmed;
}
