import { NavigationMenu as NavigationMenuPrimitive } from "@base-ui/react/navigation-menu";
import { cn } from "../../lib/utils";

function NavigationMenu({ className, ...props }: NavigationMenuPrimitive.Root.Props) {
  return <NavigationMenuPrimitive.Root className={cn("w-full", className)} {...props} />;
}

function NavigationMenuList({ className, ...props }: NavigationMenuPrimitive.List.Props) {
  return <NavigationMenuPrimitive.List className={cn("flex w-max min-w-full items-center gap-1 rounded-xl border border-border bg-card p-1 shadow-sm", className)} {...props} />;
}

function NavigationMenuItem({ className, ...props }: NavigationMenuPrimitive.Item.Props) {
  return <NavigationMenuPrimitive.Item className={cn("shrink-0", className)} {...props} />;
}

function NavigationMenuLink({ className, ...props }: NavigationMenuPrimitive.Link.Props) {
  return <NavigationMenuPrimitive.Link className={cn("inline-flex min-h-10 items-center rounded-lg px-4 py-2 text-sm font-medium text-muted-foreground outline-none transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:ring-2 focus-visible:ring-ring data-[active]:bg-primary data-[active]:text-primary-foreground", className)} {...props} />;
}

export { NavigationMenu, NavigationMenuItem, NavigationMenuLink, NavigationMenuList };
