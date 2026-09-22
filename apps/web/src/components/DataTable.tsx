import { Fragment } from "react";

import {
  flexRender,
  type ColumnDef,
  type OnChangeFn,
  type Row,
  stockFeatures,
  type StockFeatures,
  type SortingState,
  type ReactTable,
  useTable,
} from "@tanstack/react-table";

type DataTableProps<TData extends Record<string, any>> = {
  data: TData[];
  columns: ColumnDef<StockFeatures, TData, unknown>[];
  sorting?: SortingState;
  onSortingChange?: OnChangeFn<SortingState>;
  globalFilter?: string;
  onGlobalFilterChange?: OnChangeFn<string>;
  globalFilterLabel?: string;
  globalFilterPlaceholder?: string;
  getRowId?: (originalRow: TData, index: number) => string;
  selectedRowId?: string | null;
  onRowClick?: (row: Row<StockFeatures, TData>) => void;
  emptyMessage?: string;
};

function sortLabel<TData extends Record<string, any>>(table: ReactTable<StockFeatures, TData>, columnId: string) {
  const column = table.getColumn(columnId);
  if (!column?.getCanSort()) return undefined;
  const direction = column.getIsSorted();
  return direction === "asc" ? " (ascendente)" : direction === "desc" ? " (descendente)" : " (ordenar)";
}

export function DataTable<TData extends Record<string, any>>({ data, columns, sorting = [], onSortingChange, globalFilter = "", onGlobalFilterChange, globalFilterLabel = "Buscar", globalFilterPlaceholder = "Buscar…", getRowId, selectedRowId, onRowClick, emptyMessage = "No hay datos." }: DataTableProps<TData>) {
  const table = useTable({
    features: stockFeatures,
    data,
    columns,
    state: { sorting, globalFilter },
    onSortingChange,
    onGlobalFilterChange,
    manualSorting: true,
    manualFiltering: true,
    getRowId,
  });

  return <>{onGlobalFilterChange && <div className="table-global-filter"><label>{globalFilterLabel}<input value={globalFilter} placeholder={globalFilterPlaceholder} onChange={(event) => table.setGlobalFilter(event.target.value)} /></label></div>}<div className="table-wrap"><table><thead>{table.getHeaderGroups().map((headerGroup) => <Fragment key={headerGroup.id}><tr>{headerGroup.headers.map((header) => {
     const label = sortLabel(table, header.column.id);
     return <th key={header.id} aria-sort={header.column.getIsSorted() === "asc" ? "ascending" : header.column.getIsSorted() === "desc" ? "descending" : "none"}>{header.isPlaceholder ? null : header.column.getCanSort() ? <button className="table-sort-button" type="button" onClick={header.column.getToggleSortingHandler()} title={`Ordenar${label ?? ""}`}>{flexRender(header.column.columnDef.header, header.getContext())}<span aria-hidden="true">{header.column.getIsSorted() === "asc" ? " ↑" : header.column.getIsSorted() === "desc" ? " ↓" : " ↕"}</span></button> : flexRender(header.column.columnDef.header, header.getContext())}</th>;
   })}</tr></Fragment>)}</thead><tbody>{table.getRowModel().rows.map((row) => <tr key={row.id} className={selectedRowId === row.id ? "selected" : ""} onClick={() => onRowClick?.(row)}>{row.getVisibleCells().map((cell) => <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}</tr>)}{!table.getRowModel().rows.length && <tr><td colSpan={columns.length}>{emptyMessage}</td></tr>}</tbody></table></div></>;
}
