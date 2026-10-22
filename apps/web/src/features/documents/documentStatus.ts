export function isActive(status: string): boolean {
  return status === "pending" || status === "processing";
}

export function canReingest(status: string): boolean {
  return status === "ready" || status === "failed";
}
