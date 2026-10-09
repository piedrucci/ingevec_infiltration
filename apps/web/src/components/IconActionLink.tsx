import { Link, type LinkProps } from "react-router-dom";

import { cn } from "../lib/utils";

type IconActionLinkProps = LinkProps & {
  "aria-label": string;
};

export function IconActionLink({ className, ...props }: IconActionLinkProps) {
  return <Link
    className={cn(
      "inline-flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-md bg-primary text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 [&_svg]:size-5 [&_svg_path]:fill-none [&_svg_path]:stroke-current [&_svg_path]:[stroke-linecap:round] [&_svg_path]:[stroke-linejoin:round] [&_svg_path]:[stroke-width:1.8]",
      className,
    )}
    {...props}
  />;
}
