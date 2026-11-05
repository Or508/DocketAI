import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function Badge({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border border-line bg-white/80 px-2 py-0.5 text-[11px] uppercase tracking-[0.14em] text-mist",
        className,
      )}
      {...props}
    />
  );
}
