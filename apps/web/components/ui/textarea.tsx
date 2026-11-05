import * as React from "react";

import { cn } from "@/lib/utils";

export function Textarea({ className, ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "min-h-16 w-full resize-none rounded-md border border-line bg-white px-3 py-2 text-sm outline-none ring-tide/30 placeholder:text-mist/70 focus:ring-2",
        className,
      )}
      {...props}
    />
  );
}
