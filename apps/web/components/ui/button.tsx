import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-semibold transition duration-200 hover:-translate-y-0.5 disabled:pointer-events-none disabled:opacity-50 disabled:hover:translate-y-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2 focus-visible:ring-offset-paper",
  {
    variants: {
      variant: {
        default: "bg-tide text-white shadow-sm hover:bg-[#082e2c]",
        outline: "border-2 border-ink/30 bg-white text-ink hover:border-tide hover:bg-white",
        ghost: "text-ink hover:bg-black/5",
        danger: "bg-clay text-white hover:bg-[#5e2216]",
      },
      size: {
        default: "h-10",
        sm: "h-8 px-2.5 text-xs",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export function Button({ className, variant, size, asChild = false, ...props }: ButtonProps) {
  const Comp = asChild ? Slot : "button";
  return <Comp className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}
