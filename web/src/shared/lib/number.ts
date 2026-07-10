export function formatBytes(value: number) {
  if (!Number.isFinite(value) || value < 0) {
    return "-";
  }

  const units = ["B", "KB", "MB", "GB", "TB"];
  let nextValue = value;
  let unitIndex = 0;
  while (nextValue >= 1000 && unitIndex < units.length - 1) {
    nextValue /= 1000;
    unitIndex += 1;
  }

  const formatted = unitIndex === 0 ? String(nextValue) : nextValue.toFixed(nextValue >= 10 ? 1 : 2);
  return `${formatted} ${units[unitIndex]}`;
}
