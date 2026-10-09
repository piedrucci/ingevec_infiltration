import type { ComponentProps } from "react";

import { cn } from "../../lib/utils";

function Table({ className, ...props }: ComponentProps<"table">) {
  return <div data-slot="table-container" className="relative w-full overflow-auto">
    <table data-slot="table" className={cn("w-full min-w-[850px] table-auto border-collapse caption-bottom text-sm", className)} {...props} />
  </div>;
}

function TableHeader({ className, ...props }: ComponentProps<"thead">) {
  return <thead data-slot="table-header" className={cn("[&_tr]:border-b", className)} {...props} />;
}

function TableBody({ className, ...props }: ComponentProps<"tbody">) {
  return <tbody data-slot="table-body" className={cn("[&_tr:last-child]:border-0 [&_tr:nth-child(even)]:bg-muted", className)} {...props} />;
}

function TableFooter({ className, ...props }: ComponentProps<"tfoot">) {
  return <tfoot data-slot="table-footer" className={cn("border-t bg-muted/50 font-medium [&>tr]:last:border-b-0", className)} {...props} />;
}

function TableRow({ className, ...props }: ComponentProps<"tr">) {
  return <tr data-slot="table-row" className={cn("border-b border-border transition-colors hover:bg-accent data-[state=selected]:bg-accent", className)} {...props} />;
}

function TableHead({ className, ...props }: ComponentProps<"th">) {
  return <th data-slot="table-head" className={cn("h-12 border-b border-border bg-muted px-4 py-3 text-left align-middle text-xs font-bold tracking-[0.04em] text-muted-foreground uppercase [&:has([role=checkbox])]:pr-0", className)} {...props} />;
}

function TableCell({ className, ...props }: ComponentProps<"td">) {
  return <td data-slot="table-cell" className={cn("border-t border-border px-4 py-3 text-left align-middle [&:has([role=checkbox])]:pr-0", className)} {...props} />;
}

function TableCaption({ className, ...props }: ComponentProps<"caption">) {
  return <caption data-slot="table-caption" className={cn("mt-4 text-sm text-muted-foreground", className)} {...props} />;
}

export { Table, TableHeader, TableBody, TableFooter, TableHead, TableRow, TableCell, TableCaption };
