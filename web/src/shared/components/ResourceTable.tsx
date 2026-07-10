import { CSSProperties, ReactNode } from "react";
import { cx } from "../lib/className";

export type ResourceColumn<T> = {
  key: string;
  header: ReactNode;
  width: string;
  render: (row: T) => ReactNode;
};

type ResourceTableProps<T> = {
  ariaLabel: string;
  className?: string;
  columns: ResourceColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
};

export function ResourceTable<T>({ ariaLabel, className, columns, rows, rowKey }: ResourceTableProps<T>) {
  const gridTemplate: CSSProperties = {
    gridTemplateColumns: columns.map((col) => col.width).join(" "),
  };

  return (
    <div className={cx("resource-table", className)} role="table" aria-label={ariaLabel}>
      <div className="resource-table-row resource-table-head" role="row" style={gridTemplate}>
        {columns.map((col) => (
          <div key={col.key} role="columnheader">{col.header}</div>
        ))}
      </div>
      {rows.map((row) => (
        <div key={rowKey(row)} className="resource-table-row" role="row" style={gridTemplate}>
          {columns.map((col) => (
            <div key={col.key} role="cell" className={`resource-cell-${col.key}`}>
              {col.render(row)}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
