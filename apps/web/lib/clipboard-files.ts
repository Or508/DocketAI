export const DRAWER_ACCEPT = "image/*,application/pdf,.pdf,.png,.jpg,.jpeg,.webp,.heic,.bmp,.gif,.tiff";

export function filesFromTransfer(data: DataTransfer | null): File[] {
  if (!data) return [];
  const found: File[] = [];
  const seen = new Set<string>();
  const push = (file: File | null) => {
    if (!file || file.size < 0) return;
    const named = file.name
      ? file
      : new File([file], `screenshot-${Date.now()}.png`, { type: file.type || "image/png" });
    const key = `${named.name}:${named.size}:${named.type}`;
    if (seen.has(key)) return;
    seen.add(key);
    found.push(named);
  };
  for (const file of data.files) push(file);
  for (const item of data.items) {
    if (item.kind === "file") push(item.getAsFile());
  }
  return found;
}
