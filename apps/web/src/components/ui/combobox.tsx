import { Combobox as ComboboxPrimitive } from "@base-ui/react/combobox";
import { Check, ChevronDown, X } from "lucide-react";

import { cn } from "../../lib/utils";

type ComboboxOption = { value: string; label: string };

type MultiSelectComboboxProps = {
  id?: string;
  options: ComboboxOption[];
  value: string[];
  onValueChange: (value: string[]) => void;
  placeholder?: string;
  searchPlaceholder?: string;
  emptyMessage?: string;
  disabled?: boolean;
};

function MultiSelectCombobox({
  id,
  options,
  value,
  onValueChange,
  placeholder = "Selecciona opciones",
  searchPlaceholder = "Buscar…",
  emptyMessage = "No se encontraron opciones.",
  disabled,
}: MultiSelectComboboxProps) {
  const labels = new Map(options.map((option) => [option.value, option.label]));

  return (
    <ComboboxPrimitive.Root
      multiple
      autoHighlight
      value={value}
      onValueChange={(nextValue) => onValueChange(nextValue as string[])}
      items={options.map((option) => option.value)}
      itemToStringLabel={(option) => labels.get(option) ?? option}
      disabled={disabled}
    >
      <ComboboxPrimitive.Chips className="flex min-h-11 w-full flex-wrap items-center gap-1.5 rounded-xl border border-input bg-card px-3 py-2 text-sm shadow-sm outline-none transition-shadow focus-within:ring-2 focus-within:ring-ring">
        {value.map((selectedValue) => (
          <ComboboxPrimitive.Chip
            key={selectedValue}
            aria-label={labels.get(selectedValue) ?? selectedValue}
            className="inline-flex max-w-full items-center gap-1 rounded-md bg-secondary px-2 py-1 text-xs font-medium text-secondary-foreground"
          >
            <span className="truncate">{labels.get(selectedValue) ?? selectedValue}</span>
            <ComboboxPrimitive.ChipRemove
              aria-label={`Quitar ${labels.get(selectedValue) ?? selectedValue}`}
              className="inline-flex size-4 shrink-0 items-center justify-center rounded hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <X aria-hidden="true" className="size-3" />
            </ComboboxPrimitive.ChipRemove>
          </ComboboxPrimitive.Chip>
        ))}
        <ComboboxPrimitive.Input
          id={id}
          placeholder={value.length ? "Agregar otra causa…" : placeholder}
          aria-label={searchPlaceholder}
          className="min-w-36 flex-1 bg-transparent py-1 text-sm text-foreground outline-none placeholder:text-muted-foreground"
        />
        <ComboboxPrimitive.Trigger
          aria-label="Mostrar causas"
          className="inline-flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <ChevronDown aria-hidden="true" className="size-4" />
        </ComboboxPrimitive.Trigger>
      </ComboboxPrimitive.Chips>
      <ComboboxPrimitive.Portal>
        <ComboboxPrimitive.Positioner sideOffset={6} className="z-50 w-[var(--anchor-width)] outline-none">
          <ComboboxPrimitive.Popup className="max-h-72 overflow-hidden rounded-xl border border-border bg-popover text-popover-foreground shadow-lg">
            <div className="max-h-72 overflow-y-auto p-1">
              <ComboboxPrimitive.Empty className="px-3 py-6 text-center text-sm text-muted-foreground">
                {emptyMessage}
              </ComboboxPrimitive.Empty>
              <ComboboxPrimitive.List>
                {(optionValue: string) => (
                  <ComboboxPrimitive.Item
                    key={optionValue}
                    value={optionValue}
                    className={cn(
                      "relative flex cursor-default select-none items-center gap-2 rounded-lg px-3 py-2 text-sm outline-none",
                      "data-[highlighted]:bg-accent data-[highlighted]:text-accent-foreground",
                    )}
                  >
                    <span className="flex-1">{labels.get(optionValue) ?? optionValue}</span>
                    <ComboboxPrimitive.ItemIndicator>
                      <Check aria-hidden="true" className="size-4" />
                    </ComboboxPrimitive.ItemIndicator>
                  </ComboboxPrimitive.Item>
                )}
              </ComboboxPrimitive.List>
            </div>
          </ComboboxPrimitive.Popup>
        </ComboboxPrimitive.Positioner>
      </ComboboxPrimitive.Portal>
    </ComboboxPrimitive.Root>
  );
}

export { MultiSelectCombobox };
