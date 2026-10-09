import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { createSortedRowModel, flexRender, sortFn_alphanumeric, tableFeatures, type ColumnDef, type PaginationState, type SortingState, type StockFeatures, stockFeatures, useTable } from "@tanstack/react-table";
import { ChevronLeft, ChevronRight, ChevronsUpDown, Pencil } from "lucide-react";
import { useItemsByCategory } from "../../queries/postventa-items";
import type { CategoryItem } from "../../types";
import { useItemCategories, useCategoryCauses } from "./queries";
import { SearchableSelect, type SearchableOption } from "../../components/ui/searchable-select";
import { Input } from "../../components/ui/input";
import { Button } from "../../components/ui/button";
import { IconActionLink } from "../../components/IconActionLink";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../../components/ui/table";
import { Badge } from "../../components/ui/badge";
import { ErrorMessage, LoadingIndicator } from "../documents/components";

const PAGE_SIZE = 10;
const features = tableFeatures({ ...stockFeatures, sortedRowModel: createSortedRowModel(), sortFns: { alphanumeric: sortFn_alphanumeric } });

export function CategoryItemsPage() {
  const [params, setParams] = useSearchParams();
  const categoryCode = params.get("category") ?? "";
  const causeCode = params.get("cause") ?? "";
  const search = params.get("q") ?? "";
  const rawPageNumber = params.get("pageNumber");
  const requestedPageNumber = Number(rawPageNumber ?? "1");
  const pageNumber = Number.isSafeInteger(requestedPageNumber) && requestedPageNumber > 0 ? requestedPageNumber : 1;
  const [searchInput, setSearchInput] = useState(search);
  const sortId = ["project_id", "project_name", "notes"].includes(params.get("sort") ?? "") ? params.get("sort")! : "project_id";
  const sortDirection = params.get("dir") === "desc" ? "desc" : "asc";
  const update = (updates: Record<string, string | number | null>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(updates)) {
      if (value === null || value === "") next.delete(key);
      else next.set(key, String(value));
    }
    setParams(next, { replace: true });
  };

  useEffect(() => setSearchInput(search), [search]);
  useEffect(() => {
    if (categoryCode && rawPageNumber === null) update({ pageNumber: 1 });
  }, [categoryCode, rawPageNumber]);
  useEffect(() => {
    if (searchInput === search) return;
    const timer = window.setTimeout(() => update({ q: searchInput, pageNumber: 1 }), 300);
    return () => window.clearTimeout(timer);
  }, [searchInput, search, categoryCode, causeCode, sortId, sortDirection]);

  const categoriesQuery = useItemCategories();
  const causesQuery = useCategoryCauses(categoryCode || null);
  const itemsQuery = useItemsByCategory(categoryCode || null, {
    causeCode: causeCode || null,
    search,
    pageNumber,
    sortBy: sortId as "project_id" | "project_name" | "notes",
    sortDirection,
    pageSize: PAGE_SIZE,
  });
  const items = itemsQuery.data?.items ?? [];
  const total = itemsQuery.data?.total ?? 0;
  const sorting: SortingState = [{ id: sortId, desc: sortDirection === "desc" }];
  const pagination: PaginationState = { pageIndex: pageNumber - 1, pageSize: PAGE_SIZE };
  const columns = useMemo<ColumnDef<StockFeatures, CategoryItem, unknown>[]>(() => [
    { accessorKey: "project_id", header: ({ column }) => <SortHeader label="N Obra" column={column} /> },
    { accessorKey: "project_name", header: ({ column }) => <SortHeader label="Proyecto" column={column} /> },
    { accessorKey: "notes", header: ({ column }) => <SortHeader label="Observación" column={column} />, cell: ({ row }) => <span className="block max-w-[32rem] truncate" title={row.original.notes}>{row.original.notes}</span> },
    { id: "causes", header: "Causas", enableSorting: false, cell: ({ row }) => row.original.failure_causes.map((cause) => <Badge className="mr-1 mb-1" key={cause.code} variant="secondary">{cause.display_name_es}</Badge>) },
    { id: "pdf", header: "PDF", enableSorting: false, cell: ({ row }) => row.original.has_document ? "Sí" : "No" },
    { id: "action", header: "", enableSorting: false, cell: ({ row }) => <IconActionLink aria-label="Evaluar ítem" title="Evaluar ítem" to={`/items/${row.original.public_id}/evaluation?returnTo=${encodeURIComponent(`${location.pathname}${location.search}`)}`}><Pencil aria-hidden="true" /></IconActionLink> },
  ], []);
  const table = useTable({
    features,
    data: items,
    columns,
    state: { sorting, pagination },
    rowCount: total,
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
    autoResetPageIndex: false,
    onPaginationChange: (updater) => {
      const next = typeof updater === "function" ? updater(pagination) : updater;
      update({ pageNumber: next.pageIndex + 1 });
    },
    onSortingChange: (updater) => {
      const next = typeof updater === "function" ? updater(sorting) : updater;
      const first = next[0];
      update({ sort: first?.id ?? "project_id", dir: first?.desc ? "desc" : "asc", pageNumber: 1 });
    },
    getRowId: (row) => row.public_id,
  });
  const categoryOptions: SearchableOption[] = (categoriesQuery.data ?? []).map((category) => ({ value: category.code, label: `${category.display_name_es}${category.is_active ? "" : " · Inactiva"}` }));
  const causeOptions: SearchableOption[] = [
    { value: "", label: "Todas las causas" },
    ...(causesQuery.data ?? []).map((cause) => ({ value: cause.code, label: `${cause.display_name_es}${cause.is_active ? "" : " · Inactiva"}` })),
  ];
  const pageRows = table.getRowModel().rows;

  return <>
    <section className="dashboard-heading"><div><p className="eyebrow">EXPLORACIÓN DE ÍTEMS</p><h2>Ítems por categoría</h2><p className="muted">Consulta los ítems conciliados por categoría y causa.</p></div>{categoryCode && <span>{itemsQuery.data?.total.toLocaleString("es-CL") ?? "—"} ítems</span>}</section>
    <section className="mb-5 overflow-hidden rounded-[10px] border border-border bg-card shadow-sm">
      <div className="flex flex-wrap items-end gap-4 px-4 py-4 sm:px-5">
        <label className="grid min-w-64 flex-1 gap-2 font-semibold">Categoría<SearchableSelect id="category-filter" value={categoryCode} options={categoryOptions} onValueChange={(value) => update({ category: value, cause: null, pageNumber: 1 })} placeholder="Selecciona una categoría" searchPlaceholder="Buscar categoría" disabled={categoriesQuery.isLoading} /></label>
        {categoryCode && <label className="grid min-w-64 flex-1 gap-2 font-semibold">Causa<SearchableSelect id="cause-filter" value={causeCode} options={causeOptions} onValueChange={(value) => update({ cause: value || null, pageNumber: 1 })} placeholder="Todas las causas" searchPlaceholder="Buscar causa" disabled={causesQuery.isLoading} /></label>}
        {categoryCode && <label className="grid min-w-64 flex-[2_1_22rem] gap-2 font-semibold">Buscar<Input value={searchInput} placeholder="N Obra, proyecto u observación" onChange={(event) => setSearchInput(event.target.value)} /></label>}
      </div>
      {categoriesQuery.isLoading && <div className="empty-state"><LoadingIndicator label="Cargando categorías…" compact /></div>}
      <ErrorMessage error={categoriesQuery.error} />
      <ErrorMessage error={causesQuery.error} />
      <ErrorMessage error={itemsQuery.error} />
      {itemsQuery.isFetching && <div className="px-5 py-1"><LoadingIndicator label="Actualizando ítems…" compact /></div>}
      {!categoryCode ? <p className="empty-state">Selecciona una categoría para ver sus ítems.</p> : itemsQuery.isLoading ? <div className="empty-state"><LoadingIndicator label="Cargando ítems…" compact /></div> : <>
        <Table className="min-w-[680px] md:min-w-[760px]"><TableHeader>{table.getHeaderGroups().map((group) => <TableRow key={group.id} className="hover:bg-transparent">{group.headers.map((header) => <TableHead key={header.id} aria-sort={header.column.getIsSorted() === "asc" ? "ascending" : header.column.getIsSorted() === "desc" ? "descending" : "none"}>{flexRender(header.column.columnDef.header, header.getContext())}</TableHead>)}</TableRow>)}</TableHeader>
          <TableBody>{pageRows.map((row) => <TableRow key={row.id}>{row.getVisibleCells().map((cell) => <TableCell key={cell.id} className="py-0">{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>)}</TableRow>)}{!pageRows.length && <TableRow><TableCell colSpan={columns.length} className="py-4 text-center">No hay ítems asociados a esta selección.</TableCell></TableRow>}</TableBody>
        </Table>
        <div className="flex items-center justify-end gap-3 px-5 py-3"><span className="text-xs text-muted-foreground">{total ? `${(pageNumber - 1) * PAGE_SIZE + 1}–${Math.min(pageNumber * PAGE_SIZE, total)} de ${total}` : "0 ítems"}</span><div className="flex gap-2"><Button variant="outline" size="icon" aria-label="Página anterior" disabled={pageNumber <= 1} onClick={() => table.previousPage()}><ChevronLeft aria-hidden="true" /></Button><Button variant="outline" size="icon" aria-label="Página siguiente" disabled={pageNumber * PAGE_SIZE >= total} onClick={() => table.nextPage()}><ChevronRight aria-hidden="true" /></Button></div></div>
      </>}
    </section>
  </>;
}

function SortHeader({ label, column }: { label: string; column: any }) {
  return <Button variant="ghost" size="sm" className="h-auto min-h-0 justify-start rounded-none p-0 align-top leading-[inherit] hover:bg-transparent hover:text-primary" aria-label={`Ordenar por ${label}`} onClick={column.getToggleSortingHandler()}>{label}<ChevronsUpDown aria-hidden="true" className="size-3.5" /></Button>;
}
