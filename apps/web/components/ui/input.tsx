import * as React from "react";

import { cn } from "@/lib/utils";

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-11 w-full rounded-md border-2 border-ink/25 bg-white px-3 text-base text-ink outline-none transition duration-200 placeholder:text-mist/70 focus:border-tide focus:ring-2 focus:ring-tide",
        className,
      )}
      {...props}
    />
  );
}
