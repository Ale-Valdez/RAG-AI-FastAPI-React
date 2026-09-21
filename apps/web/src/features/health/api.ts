import { getJson } from "../../api/client";

export type HealthResponse = {
  status: string;
  service: string;
};

export type ReadyResponse = {
  status: string;
  probes: Record<string, boolean>;
};

export function fetchHealth() {
  return getJson<HealthResponse>("/api/health");
}

export function fetchReady() {
  return getJson<ReadyResponse>("/api/ready", [200, 503]);
}
