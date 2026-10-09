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
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table";
import { cn } from "../lib/utils";

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
  columnClassName?: (columnId: string) => string | undefined;
  tableClassName?: string;
  globalFilterClassName?: string;
  rowClassName?: (row: Row<StockFeatures, TData>) => string | undefined;
  emptyMessage?: string;
};

function sortLabel<TData extends Record<string, any>>(table: ReactTable<StockFeatures, TData>, columnId: string) {
  const column = table.getColumn(columnId);
  if (!column?.getCanSort()) return undefined;
  const direction = column.getIsSorted();
  return direction === "asc" ? " (ascendente)" : direction === "desc" ? " (descendente)" : " (ordenar)";
}

export function DataTable<TData extends Record<string, any>>({ data, columns, sorting = [], onSortingChange, globalFilter = "", onGlobalFilterChange, globalFilterLabel = "Buscar", globalFilterPlaceholder = "Buscar…", getRowId, selectedRowId, onRowClick, columnClassName, tableClassName, globalFilterClassName, rowClassName, emptyMessage = "No hay datos." }: DataTableProps<TData>) {
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

  return <>
    {onGlobalFilterChange && <div className={cn("mb-4", globalFilterClassName)}>
      <Input aria-label={globalFilterLabel} value={globalFilter} placeholder={globalFilterPlaceholder} onChange={(event) => table.setGlobalFilter(event.target.value)} />
    </div>}
    <Table className={cn("min-w-[850px]", tableClassName)}>
      <TableHeader>
        {table.getHeaderGroups().map((headerGroup) => <TableRow key={headerGroup.id} className="hover:bg-transparent">
          {headerGroup.headers.map((header) => {
            const label = sortLabel(table, header.column.id);
            return <TableHead key={header.id} className={columnClassName?.(header.column.id)} aria-sort={header.column.getIsSorted() === "asc" ? "ascending" : header.column.getIsSorted() === "desc" ? "descending" : "none"}>
              {header.isPlaceholder ? null : header.column.getCanSort()
                ? <Button variant="ghost" size="sm" className="h-auto min-h-0 justify-start rounded-none px-0 py-0 text-xs font-bold tracking-[0.04em] text-inherit uppercase hover:bg-transparent hover:text-primary" onClick={header.column.getToggleSortingHandler()} title={`Ordenar${label ?? ""}`}>
                  {flexRender(header.column.columnDef.header, header.getContext())}<span aria-hidden="true">{header.column.getIsSorted() === "asc" ? " ↑" : header.column.getIsSorted() === "desc" ? " ↓" : " ↕"}</span>
                </Button>
                : flexRender(header.column.columnDef.header, header.getContext())}
            </TableHead>;
          })}
        </TableRow>)}
      </TableHeader>
      <TableBody>
        {table.getRowModel().rows.map((row) => <TableRow key={row.id} data-state={selectedRowId === row.id ? "selected" : undefined} className={cn(onRowClick && "cursor-pointer", rowClassName?.(row))} onClick={() => onRowClick?.(row)}>
          {row.getVisibleCells().map((cell) => <TableCell key={cell.id} className={columnClassName?.(cell.column.id)}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>)}
        </TableRow>)}
        {!table.getRowModel().rows.length && <TableRow className="hover:bg-transparent"><TableCell colSpan={columns.length} className="text-center text-muted-foreground">{emptyMessage}</TableCell></TableRow>}
      </TableBody>
    </Table>
  </>;
}
