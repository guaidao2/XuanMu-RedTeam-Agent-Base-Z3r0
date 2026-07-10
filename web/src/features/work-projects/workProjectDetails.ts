export type DetailItem = [label: string, value: string | undefined];
export type FilledDetailItem = [label: string, value: string];

export function filledDetailItems(items: DetailItem[]): FilledDetailItem[] {
  return items.filter((item): item is FilledDetailItem => Boolean(item[1]));
}
