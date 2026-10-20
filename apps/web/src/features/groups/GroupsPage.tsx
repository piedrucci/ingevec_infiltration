import { useSearchParams } from "react-router-dom";
import { useFailureCauseGroups, useGroupCategories, useGroupCategoryCauses } from "../../queries/failure-cause-groups";
import { SelectableList } from "./SelectableList";

export function GroupsPage() {
  const [params, setParams] = useSearchParams();
  const groupCode = params.get("group") ?? "";
  const categoryCode = params.get("category") ?? "";
  const groupsQuery = useFailureCauseGroups();
  const categoriesQuery = useGroupCategories(groupCode || null);
  const causesQuery = useGroupCategoryCauses(groupCode || null, categoryCode || null);

  const selectGroup = (code: string) => setParams({ group: code }, { replace: true });
  const selectCategory = (code: string) => setParams({ group: groupCode, category: code }, { replace: true });

  return <>
    <section className="dashboard-heading"><div><p className="eyebrow">CATÁLOGO DE CAUSAS</p><h2>Grupos</h2><p className="muted">Consulta las categorías de cada grupo y las causas de cada categoría.</p></div></section>
    <div className="grid gap-4 md:grid-cols-3">
      <SelectableList title="Grupos" options={groupsQuery.data} selectedCode={groupCode} onSelect={selectGroup} isLoading={groupsQuery.isLoading} error={groupsQuery.error} placeholder={null} emptyMessage="No hay grupos registrados." loadingLabel="Cargando grupos…" />
      <SelectableList title="Categorías" options={groupCode ? categoriesQuery.data : undefined} selectedCode={categoryCode} onSelect={selectCategory} isLoading={categoriesQuery.isLoading} error={categoriesQuery.error} placeholder={groupCode ? null : "Selecciona un grupo para ver sus categorías."} emptyMessage="Este grupo no tiene categorías." loadingLabel="Cargando categorías…" />
      <SelectableList title="Causas" options={categoryCode ? causesQuery.data : undefined} isLoading={causesQuery.isLoading} error={causesQuery.error} placeholder={categoryCode ? null : "Selecciona una categoría para ver sus causas."} emptyMessage="Esta categoría no tiene causas en este grupo." loadingLabel="Cargando causas…" />
    </div>
  </>;
}
