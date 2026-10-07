import { Combobox } from "@base-ui/react/combobox";
import { Check, ChevronsUpDown } from "lucide-react";
import { cn } from "../../lib/utils";

export type SearchableOption = { value: string; label: string; disabled?: boolean };

export function SearchableSelect({ id, value, options, onValueChange, placeholder, searchPlaceholder, disabled }: {
  id?: string; value: string; options: SearchableOption[]; onValueChange: (value: string) => void;
  placeholder: string; searchPlaceholder: string; disabled?: boolean;
}) {
  const labels = new Map(options.map((option) => [option.value, option.label]));
  return <Combobox.Root value={value} onValueChange={(next) => { if (typeof next === "string") onValueChange(next); }} items={options.map((option) => option.value)} itemToStringLabel={(option) => labels.get(option) ?? option} disabled={disabled}>
    <div className="relative">
      <Combobox.Input id={id} placeholder={placeholder} aria-label={searchPlaceholder} className="h-11 w-full rounded-xl border border-input bg-background px-3 pr-10 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring" />
      <Combobox.Trigger aria-label="Mostrar opciones" className="absolute inset-y-0 right-2 inline-flex items-center"><ChevronsUpDown aria-hidden="true" className="size-4 text-muted-foreground" /></Combobox.Trigger>
    </div>
    <Combobox.Portal><Combobox.Positioner sideOffset={6} className="z-50 w-[var(--anchor-width)] outline-none"><Combobox.Popup className="max-h-72 overflow-auto rounded-xl border border-border bg-popover p-1 text-popover-foreground shadow-lg">
      <Combobox.Empty className="px-3 py-5 text-center text-sm text-muted-foreground">No se encontraron opciones.</Combobox.Empty>
      <Combobox.List>{(optionValue: string) => <Combobox.Item key={optionValue} value={optionValue} disabled={options.find((option) => option.value === optionValue)?.disabled} className={cn("flex cursor-default items-center gap-2 rounded-lg px-3 py-2 text-sm outline-none data-[highlighted]:bg-accent data-[disabled]:opacity-50") }>
        <span className="flex-1">{labels.get(optionValue) ?? optionValue}</span><Combobox.ItemIndicator><Check aria-hidden="true" className="size-4" /></Combobox.ItemIndicator>
      </Combobox.Item>}</Combobox.List>
    </Combobox.Popup></Combobox.Positioner></Combobox.Portal>
  </Combobox.Root>;
}
