import * as React from "react";

import { cn } from "@/lib/utils";

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-11 w-full rounded-md border border-line bg-white px-3 text-base text-ink shadow-sm outline-none transition-colors duration-150 placeholder:text-mist/70 hover:border-ink/25 focus:border-tide focus:ring-4 focus:ring-tide/10",
        className,
      )}
      {...props}
    />
  );
}
