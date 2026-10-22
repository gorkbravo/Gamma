// Instantes que llegan de la API (`retrieved_at`, `generated_at`, `created_at`…). El backend los
// genera con `now_utc()`, que es UTC sin zona, y `Date.parse` interpreta un ISO sin zona como
// hora local: en CEST un dato recién leído aparecía como "2h old" y las horas UTC se mostraban
// como locales (GUA-20261021-3). Usar solo con instantes; las fechas de barras diarias
// (`timestamp` a medianoche, `as_of`) son días de calendario y no deben pasar por aquí.
const NAIVE_ISO_DATETIME = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/;

/** Milisegundos UTC de un instante de la API; NaN si no se puede leer. */
export function parseApiInstant(value: string | null | undefined): number {
  if (!value) return Number.NaN;
  const trimmed = value.trim();
  if (NAIVE_ISO_DATETIME.test(trimmed)) {
    return Date.parse(`${trimmed.replace(" ", "T")}Z`);
  }
  return Date.parse(trimmed);
}

/** `Date` de un instante de la API, o null si no se puede leer. */
export function apiInstantDate(value: string | null | undefined): Date | null {
  const millis = parseApiInstant(value);
  return Number.isFinite(millis) ? new Date(millis) : null;
}
