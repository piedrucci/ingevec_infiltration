import { useEffect, useState } from "react";
import { createPaginatedRowModel, createSortedRowModel, flexRender, tableFeatures, type ColumnDef, type PaginationState, type SortingState, type StockFeatures, stockFeatures, useTable } from "@tanstack/react-table";
import { ArrowDownUp, ChevronDown, ChevronLeft, ChevronRight, ChevronUp } from "lucide-react";
import type { DashboardAssociationBreakdown, DashboardBreakdown, DashboardProjectProgress, DashboardSubcontractorBreakdown } from "../../types";
import { Link } from "react-router-dom";
import { useDashboardProjectProgress, useDashboardSubcontractorProjects, useDashboardSubcontractors, useDashboardSummary } from "../../queries/dashboard";
import { Button } from "../../components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../../components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../../components/ui/dialog";
import { ErrorMessage, LoadingIndicator } from "../documents/components";

const statusLabels: Record<string, string> = {
  UPLOADING: "Cargando", QUEUED: "En cola", PROCESSING: "Procesando", MATCHED: "Asociados",
  PENDING_REVIEW: "Requieren revisión", UNMATCHED: "Sin asociación", FAILED: "Con error", QUARANTINED: "En cuarentena",
};

function MetricCard({ label, value, detail }: { label: string; value: string | number; detail?: string }) {
  return <article className="rounded-[10px] border border-border bg-card p-[1.1rem] shadow-sm"><p className="text-sm text-muted-foreground">{label}</p><strong className="my-1 block text-3xl">{value}</strong>{detail && <span className="text-sm text-muted-foreground">{detail}</span>}</article>;
}

function BreakdownCard({ title, rows, total, categoryLinks = false }: { title: string; rows: DashboardBreakdown[]; total: number; categoryLinks?: boolean }) {
  return <section className="mb-0 overflow-hidden rounded-[10px] border border-border bg-card shadow-sm"><div className="flex items-center justify-between gap-4 px-5 py-4"><h2>{title}</h2><span className="text-sm text-muted-foreground">{rows.length} grupos</span></div>
    {rows.length ? <ul className="breakdown-list">{rows.map((row) => {
      const percent = total ? (row.count / total) * 100 : 0;
      return <li key={row.name}><div>{categoryLinks && row.code ? <Link to={`/items/categories?category=${encodeURIComponent(row.code)}`} title={`Ver ítems de ${row.name}`}>{row.name}</Link> : <span title={row.name}>{row.name}</span>}<strong>{row.count.toLocaleString("es-CL")} <small>({percent.toFixed(1)}%)</small></strong></div><div className="progress-track">{percent > 0 && <span style={{ width: `${percent}%` }} />}</div></li>;
    })}</ul> : <p className="empty-state">Sin datos disponibles.</p>}
  </section>;
}

const subcontractorTableFeatures = tableFeatures({ ...stockFeatures, sortedRowModel: createSortedRowModel(), paginatedRowModel: createPaginatedRowModel() });
const managerProgressTableFeatures = tableFeatures({ ...stockFeatures, sortedRowModel: createSortedRowModel() });
const projectProgressTableFeatures = tableFeatures({ ...stockFeatures, sortedRowModel: createSortedRowModel(), paginatedRowModel: createPaginatedRowModel() });
const subcontractorColumns: ColumnDef<StockFeatures, DashboardSubcontractorBreakdown, unknown>[] = [
  { accessorKey: "name", header: ({ column }) => <SortableHeader label="Subcontratista" direction={column.getIsSorted()} onToggle={() => column.toggleSorting(column.getIsSorted() === "asc")} /> },
  { accessorKey: "speciality", header: ({ column }) => <SortableHeader label="Especialidad" direction={column.getIsSorted()} onToggle={() => column.toggleSorting(column.getIsSorted() === "asc")} /> },
  { accessorKey: "project_count", header: ({ column }) => <SortableHeader label="Proyectos" direction={column.getIsSorted()} onToggle={() => column.toggleSorting(column.getIsSorted() === "asc")} />, cell: ({ getValue }) => Number(getValue()).toLocaleString("es-CL") },
];

function SubcontractorCard() {
  const query = useDashboardSubcontractors();
  const rows = query.data ?? [];
  const [selectedSubcontractor, setSelectedSubcontractor] = useState<DashboardSubcontractorBreakdown | null>(null);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 10 });
  const [sorting, setSorting] = useState<SortingState>([{ id: "project_count", desc: true }]);
  useEffect(() => {
    setPagination((current) => ({ ...current, pageIndex: Math.min(current.pageIndex, Math.max(0, Math.ceil(rows.length / current.pageSize) - 1)) }));
  }, [rows.length]);
  const table = useTable({
    features: subcontractorTableFeatures,
    data: rows,
    columns: subcontractorColumns,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    getRowId: (row) => row.name,
  });
  const pageRows = table.getRowModel().rows;
  const projectQuery = useDashboardSubcontractorProjects(selectedSubcontractor?.id ?? null);

  return <section className="mb-0 overflow-hidden rounded-[10px] border border-border bg-card shadow-sm">
    <div className="flex items-center justify-between gap-4 px-5 py-4"><h2>Proyectos por subcontratista</h2><span className="text-sm text-muted-foreground">{query.isLoading ? "Cargando…" : `${rows.length} subcontratistas`}</span></div>
    <ErrorMessage error={query.error} />
    {query.isLoading ? <div className="empty-state"><LoadingIndicator label="Cargando subcontratistas…" compact /></div> : rows.length ? <>
      <Table className="min-w-0 table-fixed">
          <TableHeader>{table.getHeaderGroups().map((group) => <TableRow key={group.id} className="hover:bg-transparent">{group.headers.map((header) => <TableHead key={header.id} aria-sort={header.column.getIsSorted() === "asc" ? "ascending" : header.column.getIsSorted() === "desc" ? "descending" : "none"} className={header.column.id === "name" ? "w-[42%]" : header.column.id === "speciality" ? "w-[38%]" : "w-[20%] text-right"}>{flexRender(header.column.columnDef.header, header.getContext())}</TableHead>)}</TableRow>)}</TableHeader>
          <TableBody>
            {pageRows.map((row) => <TableRow key={row.id} className="cursor-pointer focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-[-2px]" tabIndex={0} aria-label={`Ver proyectos de ${row.original.name}`} onClick={() => setSelectedSubcontractor(row.original)} onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                setSelectedSubcontractor(row.original);
              }
            }}>
              {row.getVisibleCells().map((cell) => <TableCell key={cell.id} className={cell.column.id === "name" ? "w-[42%]" : cell.column.id === "speciality" ? "w-[38%]" : "w-[20%] text-right tabular-nums"}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>)}
            </TableRow>)}
          </TableBody>
        </Table>
      <div className="flex items-center justify-between gap-3 border-t border-border px-4 py-3">
        <span className="text-xs text-muted-foreground">{`${pagination.pageIndex * pagination.pageSize + 1}–${Math.min((pagination.pageIndex + 1) * pagination.pageSize, rows.length)} de ${rows.length}`}</span>
        <div className="flex gap-2">
          <Button variant="outline" size="icon" aria-label="Página anterior" title="Página anterior" disabled={!table.getCanPreviousPage()} onClick={() => table.previousPage()}><ChevronLeft aria-hidden="true" /></Button>
          <Button variant="outline" size="icon" aria-label="Página siguiente" title="Página siguiente" disabled={!table.getCanNextPage()} onClick={() => table.nextPage()}><ChevronRight aria-hidden="true" /></Button>
        </div>
      </div>
    </> : <p className="empty-state">Sin datos disponibles.</p>}
    <Dialog open={selectedSubcontractor !== null} onOpenChange={(open) => { if (!open) setSelectedSubcontractor(null); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{selectedSubcontractor?.name}</DialogTitle>
          <DialogDescription>{selectedSubcontractor?.speciality} · {selectedSubcontractor?.project_count.toLocaleString("es-CL")} proyectos asociados</DialogDescription>
        </DialogHeader>
        {projectQuery.isLoading ? <div className="py-3"><LoadingIndicator label="Cargando proyectos…" compact /></div> : projectQuery.error ? <ErrorMessage error={projectQuery.error} /> : projectQuery.data?.length ? <Table className="min-w-0">
          <TableHeader><TableRow><TableHead>N° Obra</TableHead><TableHead>Proyecto</TableHead></TableRow></TableHeader>
          <TableBody>{projectQuery.data.map((project) => <TableRow key={project.project_id}><TableCell className="tabular-nums">{project.project_id}</TableCell><TableCell>{project.project_name}</TableCell></TableRow>)}</TableBody>
        </Table> : <p className="empty-state dialog-empty">No hay proyectos asociados a este subcontratista.</p>}
      </DialogContent>
    </Dialog>
  </section>;
}

function SortableHeader({ label, direction, onToggle }: { label: string; direction: false | "asc" | "desc"; onToggle: () => void }) {
  const Icon = direction === "asc" ? ChevronUp : direction === "desc" ? ChevronDown : ArrowDownUp;
  return <Button variant="ghost" size="sm" className="h-auto min-h-0 whitespace-nowrap rounded-none px-1 py-0 text-[0.7rem] uppercase tracking-[0.03em] hover:bg-transparent hover:text-primary" aria-label={`Ordenar por ${label}`} onClick={onToggle}>
    {label}<Icon aria-hidden="true" />
  </Button>;
}

const managerProgressColumns: ColumnDef<StockFeatures, DashboardAssociationBreakdown, unknown>[] = [
  { accessorKey: "name", header: ({ column }) => <SortableHeader label="Gerente de proyecto" direction={column.getIsSorted()} onToggle={() => column.toggleSorting(column.getIsSorted() === "asc")} />, cell: ({ row }) => row.original.project_manager_id !== null ? <Link className="manager-link" to={`/project-managers/${row.original.project_manager_id}/items`}>{row.original.name}</Link> : row.original.name },
  { accessorKey: "items", header: ({ column }) => <SortableHeader label="Ítems" direction={column.getIsSorted()} onToggle={() => column.toggleSorting(column.getIsSorted() === "asc")} />, cell: ({ getValue }) => Number(getValue()).toLocaleString("es-CL") },
  { accessorKey: "reconciled_items", header: ({ column }) => <SortableHeader label="Conciliados" direction={column.getIsSorted()} onToggle={() => column.toggleSorting(column.getIsSorted() === "asc")} />, cell: ({ getValue }) => Number(getValue()).toLocaleString("es-CL") },
  { accessorKey: "pending_reconciliation_items", header: ({ column }) => <SortableHeader label="Pendientes" direction={column.getIsSorted()} onToggle={() => column.toggleSorting(column.getIsSorted() === "asc")} />, cell: ({ getValue }) => Number(getValue()).toLocaleString("es-CL") },
  { accessorKey: "reconciliation_rate", header: ({ column }) => <SortableHeader label="Avance" direction={column.getIsSorted()} onToggle={() => column.toggleSorting(column.getIsSorted() === "asc")} />, cell: ({ getValue }) => {
    const rate = Number(getValue());
    return <div className="min-w-[180px] [&>div]:grid [&>div]:grid-cols-[3.8rem_minmax(80px,1fr)] [&>div]:items-center [&>div]:gap-2 [&_strong]:text-sm"><div><strong>{(rate * 100).toFixed(1)}%</strong><div className="progress-track">{rate > 0 && <span style={{ width: `${rate * 100}%` }} />}</div></div></div>;
  } },
  { accessorKey: "associated_items", header: "Con PDF", enableSorting: false, cell: ({ getValue }) => Number(getValue()).toLocaleString("es-CL") },
];

function ProjectManagerProgressCard({ rows }: { rows: DashboardAssociationBreakdown[] }) {
  const [sorting, setSorting] = useState<SortingState>([{ id: "pending_reconciliation_items", desc: true }]);
  const table = useTable({
    features: managerProgressTableFeatures,
    data: rows,
    columns: managerProgressColumns,
    state: { sorting },
    onSortingChange: setSorting,
  });
  return <section className="mb-4 overflow-hidden rounded-[10px] border border-border bg-card shadow-sm"><div className="flex items-center justify-between gap-4 px-5 py-4"><div><h2>Avance por gerente de proyecto</h2><p className="muted mt-1">Ítems conciliados mediante una o más causas</p></div><span className="text-sm text-muted-foreground">{rows.length} gerentes</span></div>
    {rows.length ? <Table className="min-w-[1000px]"><TableHeader>{table.getHeaderGroups().map((group) => <TableRow key={group.id} className="hover:bg-transparent">{group.headers.map((header) => <TableHead key={header.id} aria-sort={header.column.getIsSorted() === "asc" ? "ascending" : header.column.getIsSorted() === "desc" ? "descending" : "none"}>{flexRender(header.column.columnDef.header, header.getContext())}</TableHead>)}</TableRow>)}</TableHeader><TableBody>{table.getRowModel().rows.map((row) => <TableRow key={row.id}>{row.getVisibleCells().map((cell) => <TableCell key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>)}</TableRow>)}</TableBody></Table> : <p className="empty-state">Sin datos disponibles.</p>}
  </section>;
}

const PROJECT_PAGE_SIZE = 20;
const projectProgressColumns: ColumnDef<StockFeatures, DashboardProjectProgress, unknown>[] = [
  { accessorKey: "name", header: ({ column }) => <SortableHeader label="Proyecto" direction={column.getIsSorted()} onToggle={() => column.toggleSorting(column.getIsSorted() === "asc")} />, cell: ({ row }) => <Link className="manager-link" to={`/projects?project=${encodeURIComponent(row.original.project_id)}`}>{row.original.name}</Link> },
  { accessorKey: "items", header: ({ column }) => <SortableHeader label="Ítems" direction={column.getIsSorted()} onToggle={() => column.toggleSorting(column.getIsSorted() === "asc")} />, cell: ({ getValue }) => Number(getValue()).toLocaleString("es-CL") },
  { accessorKey: "conciliated", header: ({ column }) => <SortableHeader label="Conciliados" direction={column.getIsSorted()} onToggle={() => column.toggleSorting(column.getIsSorted() === "asc")} />, cell: ({ getValue }) => Number(getValue()).toLocaleString("es-CL") },
  { accessorKey: "pending", header: ({ column }) => <SortableHeader label="Pendientes" direction={column.getIsSorted()} onToggle={() => column.toggleSorting(column.getIsSorted() === "asc")} />, cell: ({ getValue }) => Number(getValue()).toLocaleString("es-CL") },
  { accessorKey: "percentage", header: ({ column }) => <SortableHeader label="Porcentaje" direction={column.getIsSorted()} onToggle={() => column.toggleSorting(column.getIsSorted() === "asc")} />, cell: ({ getValue }) => {
    const percentage = Number(getValue());
    return <div className="min-w-[180px] [&>div]:grid [&>div]:grid-cols-[3.8rem_minmax(80px,1fr)] [&>div]:items-center [&>div]:gap-2 [&_strong]:text-sm"><div><strong>{percentage.toFixed(1)}%</strong><div className="progress-track">{percentage > 0 && <span style={{ width: `${percentage}%` }} />}</div></div></div>;
  } },
];

function ProjectProgressCard() {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: PROJECT_PAGE_SIZE });
  const [sorting, setSorting] = useState<SortingState>([{ id: "items", desc: true }]);
  const sort = sorting[0] ?? { id: "items", desc: true };
  const query = useDashboardProjectProgress({
    limit: pagination.pageSize,
    offset: pagination.pageIndex * pagination.pageSize,
    sortBy: sort.id,
    sortDirection: sort.desc ? "desc" : "asc",
  });
  const rows = query.data?.items ?? [];
  const total = query.data?.page.total ?? 0;
  const table = useTable({
    features: projectProgressTableFeatures,
    data: rows,
    columns: projectProgressColumns,
    state: { pagination, sorting },
    rowCount: total,
    manualPagination: true,
    manualSorting: true,
    autoResetPageIndex: false,
    onPaginationChange: setPagination,
    onSortingChange: (updater) => {
      setSorting(updater);
      setPagination((current) => ({ ...current, pageIndex: 0 }));
    },
    getRowId: (row) => row.project_id,
  });

  return <section className="mb-4 overflow-hidden rounded-[10px] border border-border bg-card shadow-sm">
    <div className="flex items-center justify-between gap-4 px-5 py-4"><h2>Proyectos</h2><span className="text-sm text-muted-foreground">{query.isLoading ? "Cargando…" : `${total.toLocaleString("es-CL")} proyectos`}</span></div>
    <ErrorMessage error={query.error} />
    {query.isLoading ? <div className="px-5 py-4"><LoadingIndicator label="Cargando proyectos…" compact /></div> : rows.length ? <>
      <Table className="min-w-[760px]"><TableHeader>{table.getHeaderGroups().map((group) => <TableRow key={group.id} className="hover:bg-transparent">{group.headers.map((header) => <TableHead key={header.id} aria-sort={header.column.getIsSorted() === "asc" ? "ascending" : header.column.getIsSorted() === "desc" ? "descending" : "none"} className={header.column.id === "name" ? "w-[44%]" : "text-right"}>{flexRender(header.column.columnDef.header, header.getContext())}</TableHead>)}</TableRow>)}</TableHeader>
        <TableBody>{table.getRowModel().rows.map((row) => <TableRow key={row.id}>{row.getVisibleCells().map((cell) => <TableCell key={cell.id} className={cell.column.id === "name" ? "w-[44%]" : "text-right tabular-nums"}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>)}</TableRow>)}</TableBody>
      </Table>
      <div className="flex items-center justify-end gap-3 px-5 py-3"><span className="text-xs text-muted-foreground">{`${pagination.pageIndex * pagination.pageSize + 1}–${Math.min((pagination.pageIndex + 1) * pagination.pageSize, total)} de ${total}`}</span><div className="flex gap-2"><Button variant="outline" size="icon" aria-label="Página anterior de proyectos" disabled={!table.getCanPreviousPage() || query.isFetching} onClick={() => table.previousPage()}><ChevronLeft aria-hidden="true" /></Button><Button variant="outline" size="icon" aria-label="Página siguiente de proyectos" disabled={!table.getCanNextPage() || query.isFetching} onClick={() => table.nextPage()}><ChevronRight aria-hidden="true" /></Button></div></div>
    </> : <p className="px-5 py-4 text-sm text-muted-foreground">No hay proyectos disponibles.</p>}
  </section>;
}

export function HomePage() {
  const summaryQuery = useDashboardSummary();
  const summary = summaryQuery.data;
  if (summaryQuery.isLoading) return <div className="loading-block"><LoadingIndicator label="Preparando resumen…" /></div>;
  if (!summary) return <ErrorMessage error={summaryQuery.error || new Error("No fue posible obtener el resumen.")} />;
  const { totals, breakdowns } = summary;
  const lastUpdated = new Intl.DateTimeFormat("es-CL", { dateStyle: "short", timeStyle: "short" }).format(new Date(summary.generated_at));

  return <>
    <section className="dashboard-heading"><div><p className="eyebrow">RESUMEN EJECUTIVO</p><h2>Estado de postventa</h2><p className="muted">Actualizado: {lastUpdated}</p></div>{summaryQuery.isFetching && <LoadingIndicator label="Actualizando…" compact />}</section>
    <section className="metric-grid">
      <MetricCard label="Ítems totales" value={totals.items.toLocaleString("es-CL")} />
      <MetricCard label="Ítems conciliados" value={totals.reconciled_items.toLocaleString("es-CL")} detail={`${(totals.reconciliation_rate * 100).toFixed(1)}% de avance`} />
      <MetricCard label="Pendientes de conciliación" value={totals.pending_reconciliation_items.toLocaleString("es-CL")} detail="Sin causas asignadas" />
      <MetricCard label="Cobertura documental" value={totals.associated_items.toLocaleString("es-CL")} detail={`${(totals.document_coverage_rate * 100).toFixed(1)}% con PDF`} />
      <MetricCard label="PDFs registrados" value={totals.documents.toLocaleString("es-CL")} />
    </section>
    <section className="mb-5 overflow-hidden rounded-[10px] border border-border bg-card shadow-sm"><div className="flex items-center justify-between gap-4 px-5 py-4"><h2>Avance de conciliación</h2><span className="text-sm text-muted-foreground">{(totals.reconciliation_rate * 100).toFixed(1)}%</span></div><div className="px-5 pb-5"><div className="progress-track large"><span style={{ width: `${totals.reconciliation_rate * 100}%` }} /></div><p className="muted mt-2">{totals.reconciled_items.toLocaleString("es-CL")} conciliados · {totals.pending_reconciliation_items.toLocaleString("es-CL")} pendientes</p></div></section>
    <ProjectManagerProgressCard rows={summary.project_manager_association_progress ?? []} />
    <ProjectProgressCard />
    <section className="dashboard-grid">
      <BreakdownCard title="Ítems por gerente divisional" rows={breakdowns.division_managers ?? []} total={totals.items} />
      <BreakdownCard title="Ítems por gerente de proyecto" rows={breakdowns.project_managers ?? []} total={totals.items} />
      <BreakdownCard title="Ítems por clasificación" rows={breakdowns.classifications ?? []} total={totals.items} />
      <BreakdownCard title="Items por Categoria" rows={breakdowns.failure_cause_categories ?? []} total={totals.items} categoryLinks />
      <SubcontractorCard />
      <BreakdownCard title="Ítems por responsable" rows={breakdowns.handled_by ?? []} total={totals.items} />
      <BreakdownCard title="PDFs por estado" rows={Object.entries(totals.documents_by_status).map(([name, count]) => ({ name: statusLabels[name] ?? name, count }))} total={totals.documents} />
    </section>
  </>;
}
