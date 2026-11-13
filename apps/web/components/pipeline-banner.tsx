import type { PipelineProgress } from "@docketai/shared-types";

const labels: Record<PipelineProgress["stage"], string> = {
  draft: "טיוטה",
  parsing: "קריאה",
  classifying: "סיווג",
  auditing: "בדיקה",
  awaiting_input: "ממתין למשרד",
  ready_for_signature: "מוכן לחתימה",
  signed: "נחתם",
  failed: "דורש תשומת לב",
};

export function PipelineBanner({ pipeline }: { pipeline: PipelineProgress }) {
  const count =
    pipeline.stage === "classifying" && pipeline.total > 0
      ? `${Math.min(pipeline.completed + 1, pipeline.total)}/${pipeline.total}`
      : "";
  const title = count ? `${labels[pipeline.stage]}: ${count}` : labels[pipeline.stage];
  return (
    <div className="mt-4 flex flex-wrap items-baseline justify-between gap-2 rounded-md border border-line bg-white/70 px-4 py-3">
      <p className="text-sm font-medium">{title}</p>
      {pipeline.message ? <p className="text-sm text-mist">{pipeline.message}</p> : null}
    </div>
  );
}
