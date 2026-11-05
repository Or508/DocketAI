import type { CaseStatus } from "@docketai/shared-types";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const copy: Record<CaseStatus, string> = {
  draft: "Draft",
  processing: "Processing",
  ready_for_review: "Needs review",
  filling: "Ready to fill",
  signed: "Signed",
  failed: "Failed",
};

const tone: Record<CaseStatus, string> = {
  draft: "text-mist",
  processing: "border-tide/30 text-tide",
  ready_for_review: "border-amberink/30 text-amberink",
  filling: "border-tide/30 text-tide",
  signed: "border-moss/30 text-moss",
  failed: "border-clay/30 text-clay",
};

export function StatusPill({ status }: { status: CaseStatus }) {
  return <Badge className={cn(tone[status])}>{copy[status]}</Badge>;
}
