import type { AdminStats, VerificationDetail, VerificationListItem, WebhookDelivery } from "./types";

let ADMIN_TOKEN = localStorage.getItem("ADMIN_TOKEN");
if (!ADMIN_TOKEN) {
  const t = prompt("Please enter the Admin Token:");
  if (t) {
    ADMIN_TOKEN = t;
    localStorage.setItem("ADMIN_TOKEN", t);
  } else {
    ADMIN_TOKEN = "admin-secret-change-me";
  }
}

export function clearToken() {
  localStorage.removeItem("ADMIN_TOKEN");
  window.location.reload();
}

const BASE = "/admin";

export const headers = {
  "Content-Type": "application/json",
  Authorization: `Bearer ${ADMIN_TOKEN}`,
};

export async function fetchVerifications(params?: {
  status?: string;
  doc_type?: string;
  country?: string;
  page?: number;
}): Promise<{ items: VerificationListItem[]; total: number }> {
  const q = new URLSearchParams();
  if (params?.status) q.set("status", params.status);
  if (params?.doc_type) q.set("doc_type", params.doc_type);
  if (params?.country) q.set("country", params.country);
  if (params?.page) q.set("page", String(params.page));
  const res = await fetch(`${BASE}/verifications?${q}`, { headers });
  if (res.status === 403) clearToken();
  if (!res.ok) throw new Error("Failed to fetch verifications");
  return res.json();
}

export async function fetchVerification(id: string): Promise<VerificationDetail> {
  const res = await fetch(`${BASE}/verifications/${id}`, { headers });
  if (res.status === 403) clearToken();
  if (!res.ok) throw new Error("Verification not found");
  return res.json();
}

export async function approveVerification(id: string, notes?: string): Promise<void> {
  const res = await fetch(`${BASE}/verifications/${id}/approve`, {
    method: "POST",
    headers,
    body: JSON.stringify({ notes }),
  });
  if (res.status === 403) clearToken();
  if (!res.ok) {
    const error = await res.text().catch(() => "Unknown error");
    throw new Error(error || `Failed to approve (${res.status})`);
  }
}

export async function rejectVerification(id: string, reason: string, fraud_flag = false): Promise<void> {
  const res = await fetch(`${BASE}/verifications/${id}/reject`, {
    method: "POST",
    headers,
    body: JSON.stringify({ reason, fraud_flag }),
  });
  if (res.status === 403) clearToken();
  if (!res.ok) {
    const error = await res.text().catch(() => "Unknown error");
    throw new Error(error || `Failed to reject (${res.status})`);
  }
}

export async function fetchFrames(id: string): Promise<string[]> {
  const res = await fetch(`${BASE}/verifications/${id}/frames`, { headers });
  if (res.status === 403) clearToken();
  if (!res.ok) return [];
  const data = await res.json();
  return data.urls ?? [];
}

export async function fetchStats(): Promise<AdminStats> {
  const res = await fetch(`${BASE}/stats`, { headers });
  if (res.status === 403) clearToken();
  if (!res.ok) throw new Error("Failed to fetch stats");
  return res.json();
}

export async function fetchWebhooks(id: string): Promise<WebhookDelivery[]> {
  const res = await fetch(`${BASE}/webhooks/${id}`, { headers });
  if (res.status === 403) clearToken();
  if (!res.ok) return [];
  return res.json();
}

export async function resendWebhook(id: string): Promise<void> {
  const res = await fetch(`${BASE}/verifications/${id}/resend-webhook`, {
    method: "POST",
    headers,
  });
  if (res.status === 403) clearToken();
  if (!res.ok) {
    const error = await res.text().catch(() => "Unknown error");
    throw new Error(error || `Failed to resend webhook (${res.status})`);
  }
}

export async function createVerification(data: {
  user_id: string;
  document_type: string;
  front_image: File;
  back_image?: File;
}): Promise<{ verification_id: string; status: string; doc_type: string; user_id: string }> {
  const formData = new FormData();
  formData.append("user_id", data.user_id);
  formData.append("document_type", data.document_type);
  formData.append("front_image", data.front_image);
  if (data.back_image) {
    formData.append("back_image", data.back_image);
  }

  const res = await fetch(`${BASE}/verifications/create`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${ADMIN_TOKEN}`,
    },
    body: formData,
  });
  if (res.status === 403) clearToken();
  if (!res.ok) {
    const error = await res.text();
    throw new Error(error || "Failed to create verification");
  }
  return res.json();
}
