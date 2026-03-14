import type { OpportunitiesResponse, ScanRequest, ScanResponse } from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json"
    },
    ...init
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }

  return (await response.json()) as T;
}

export function fetchOpportunities(): Promise<OpportunitiesResponse> {
  return requestJson<OpportunitiesResponse>("/opportunities");
}

export function runScan(payload: ScanRequest): Promise<ScanResponse> {
  return requestJson<ScanResponse>("/scan", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}
