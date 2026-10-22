/**
 * Texto enriquecido mínimo de Copilot (GUA-20261021-13).
 *
 * Los campos de la tarjeta llegan como texto plano que a veces contiene tablas Markdown;
 * renderizadas dentro de un párrafo se veían como tuberías `| Delivery | Brent |`. Este
 * analizador devuelve segmentos estructurados (párrafo, lista, tabla) que el componente
 * pinta con plantillas Svelte escapadas: nunca se inserta HTML del modelo.
 */

export type CopilotTextAlign = "left" | "right" | "center" | null;

export type CopilotTextSegment =
  | { kind: "paragraph"; text: string }
  | { kind: "list"; ordered: boolean; items: string[] }
  | { kind: "table"; header: string[]; align: CopilotTextAlign[]; rows: string[][] };

const TABLE_SEPARATOR = /^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$/;
const BULLET = /^\s*[-*•]\s+(.*)$/;
const NUMBERED = /^\s*\d{1,2}[.)]\s+(.*)$/;

/** Quita marcas de énfasis Markdown que no se renderizan (negrita, código en línea). */
function stripInlineMarkup(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/__(.+?)__/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .trim();
}

function splitRow(line: string): string[] {
  const cells: string[] = [];
  let current = "";
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    if (char === "\\" && line[index + 1] === "|") {
      current += "|";
      index += 1;
    } else if (char === "|") {
      cells.push(current);
      current = "";
    } else {
      current += char;
    }
  }
  cells.push(current);
  const trimmed = line.trim();
  if (trimmed.startsWith("|")) cells.shift();
  if (trimmed.endsWith("|") && !trimmed.endsWith("\\|")) cells.pop();
  return cells.map((cell) => stripInlineMarkup(cell));
}

function alignment(cell: string): CopilotTextAlign {
  const value = cell.trim();
  const left = value.startsWith(":");
  const right = value.endsWith(":");
  if (left && right) return "center";
  if (right) return "right";
  if (left) return "left";
  return null;
}

function isTableStart(lines: string[], index: number): boolean {
  const header = lines[index];
  const separator = lines[index + 1];
  if (header == null || separator == null) return false;
  if (!header.includes("|") || !TABLE_SEPARATOR.test(separator) || !separator.includes("-")) return false;
  return splitRow(header).length >= 2;
}

export function parseCopilotRichText(value: string | null | undefined): CopilotTextSegment[] {
  const lines = String(value ?? "").replace(/\r\n?/g, "\n").split("\n");
  const segments: CopilotTextSegment[] = [];
  let paragraph: string[] = [];

  const flushParagraph = () => {
    const text = paragraph.map(stripInlineMarkup).join("\n").trim();
    if (text) segments.push({ kind: "paragraph", text });
    paragraph = [];
  };

  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      flushParagraph();
      index += 1;
      continue;
    }
    if (isTableStart(lines, index)) {
      flushParagraph();
      const header = splitRow(line);
      const align = splitRow(lines[index + 1]).map(alignment);
      const rows: string[][] = [];
      index += 2;
      while (index < lines.length && lines[index].trim() && lines[index].includes("|")) {
        const cells = splitRow(lines[index]);
        // Filas cortas se rellenan para que la rejilla no se desalinee.
        rows.push(header.map((_, column) => cells[column] ?? ""));
        index += 1;
      }
      segments.push({ kind: "table", header, align: header.map((_, column) => align[column] ?? null), rows });
      continue;
    }
    const bullet = BULLET.exec(line);
    const numbered = bullet ? null : NUMBERED.exec(line);
    if (bullet || numbered) {
      flushParagraph();
      const ordered = numbered != null;
      const items: string[] = [];
      while (index < lines.length) {
        const match = ordered ? NUMBERED.exec(lines[index]) : BULLET.exec(lines[index]);
        if (!match) break;
        const item = stripInlineMarkup(match[1]);
        if (item) items.push(item);
        index += 1;
      }
      if (items.length) segments.push({ kind: "list", ordered, items });
      continue;
    }
    paragraph.push(line);
    index += 1;
  }
  flushParagraph();
  return segments;
}

/** Celdas numéricas (precios, porcentajes, diferenciales) se alinean a la derecha. */
export function isNumericCell(value: string): boolean {
  return /^[-+−]?[$€£]?\s?\d[\d,]*(\.\d+)?\s?(%|pp|bp|bps|x)?$/i.test(value.trim());
}

export function hasCopilotText(value: string | null | undefined): boolean {
  return String(value ?? "").trim().length > 0;
}
