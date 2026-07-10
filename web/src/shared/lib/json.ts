export function stableJson(value: unknown): string {
  try {
    return JSON.stringify(sortJson(value));
  } catch {
    return String(value);
  }
}

function sortJson(value: unknown): unknown {
  if (!value || typeof value !== "object") return value;
  if (Array.isArray(value)) return value.map(sortJson);
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => [key, sortJson(item)]),
  );
}
