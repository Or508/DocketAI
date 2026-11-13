import type { FolderTone } from "@/lib/filing";
import { FOLDER_LABEL } from "@/lib/filing";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const tone: Record<FolderTone, string> = {
  missing: "border-amberink bg-[#f6e4c4] text-[#4a3208]",
  review: "border-tide bg-[#d5ece9] text-[#062725]",
  awaiting: "border-[#062725] bg-tide text-white",
  done: "border-[#0c3d28] bg-moss text-white",
};

export function StatusPill({ tone: folder }: { tone: FolderTone }) {
  return <Badge className={cn(tone[folder])}>{FOLDER_LABEL[folder]}</Badge>;
}
