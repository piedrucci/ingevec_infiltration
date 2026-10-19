import { Badge } from "../../components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { cn } from "../../lib/utils";
import { ErrorMessage, LoadingIndicator } from "../documents/components";

export type SelectableListOption = { code: string; display_name_es: string; is_active?: boolean };

type SelectableListProps = {
  title: string;
  options: SelectableListOption[] | undefined;
  selectedCode?: string;
  onSelect?: (code: string) => void;
  isLoading: boolean;
  error: unknown;
  placeholder: string | null;
  emptyMessage: string;
  loadingLabel: string;
};

export function SelectableList({ title, options, selectedCode, onSelect, isLoading, error, placeholder, emptyMessage, loadingLabel }: SelectableListProps) {
  return <Card className="gap-4 py-5">
    <CardHeader className="px-5"><CardTitle className="text-base">{title}{options && <span className="ml-2 text-sm font-normal text-muted-foreground">({options.length})</span>}</CardTitle></CardHeader>
    <CardContent className="px-3">
      {placeholder ? <p className="px-2 py-4 text-sm text-muted-foreground">{placeholder}</p>
        : isLoading ? <div className="px-2 py-4"><LoadingIndicator label={loadingLabel} compact /></div>
        : error ? <ErrorMessage error={error} />
        : !options?.length ? <p className="px-2 py-4 text-sm text-muted-foreground">{emptyMessage}</p>
        : <ul className="grid max-h-[60vh] gap-1 overflow-y-auto">
          {options.map((option) => {
            const selected = option.code === selectedCode;
            const label = <>
              <span className="min-w-0 flex-1 truncate" title={option.display_name_es}>{option.display_name_es}</span>
              {option.is_active === false && <Badge variant="outline">Inactiva</Badge>}
            </>;
            return <li key={option.code}>
              {onSelect
                ? <button type="button" aria-pressed={selected} onClick={() => onSelect(option.code)} className={cn("flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring", selected && "bg-primary text-primary-foreground hover:bg-primary")}>{label}</button>
                : <div className="flex items-center gap-2 px-3 py-2 text-sm">{label}</div>}
            </li>;
          })}
        </ul>}
    </CardContent>
  </Card>;
}
