import * as React from "react";

import { cn } from "@/lib/utils";

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-10 w-full rounded-md border border-line bg-white px-3 text-sm outline-none ring-tide/30 placeholder:text-mist/70 focus:ring-2",
        className,
      )}
      {...props}
    />
  );
}
