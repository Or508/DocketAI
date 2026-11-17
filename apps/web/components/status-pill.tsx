import type { FolderTone } from "@/lib/filing";
import { FOLDER_LABEL } from "@/lib/filing";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

// Soft tints with a coloured dot: the state reads at a glance without shouting.
const tone: Record<FolderTone, { pill: string; dot: string }> = {
  missing: { pill: "border-[#f1dfbd] bg-[#fdf5e6] text-[#7a4f0f]", dot: "bg-[#d4952b]" },
  review: { pill: "border-[#cfe5e1] bg-mint text-tide", dot: "bg-tide" },
  awaiting: { pill: "border-[#d6e0f5] bg-[#eef3fc] text-[#24427f]", dot: "bg-[#3b65c4]" },
  done: { pill: "border-[#cde8d7] bg-[#ebf6ef] text-moss", dot: "bg-moss" },
};

export function StatusPill({ tone: folder }: { tone: FolderTone }) {
  return (
    <Badge className={cn(tone[folder].pill)}>
      <span aria-hidden className={cn("h-1.5 w-1.5 rounded-full", tone[folder].dot)} />
      {FOLDER_LABEL[folder]}
    </Badge>
  );
}
