import type { AdminStats, VerificationDetail, VerificationListItem, WebhookDelivery } from "./types";

const ADMIN_TOKEN = import.meta.env.VITE_ADMIN_TOKEN ?? "admin-secret-change-me";
const BASE = "/admin";

const headers = {
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
  if (!res.ok) throw new Error("Failed to fetch verifications");
  return res.json();
}

export async function fetchVerification(id: string): Promise<VerificationDetail> {
  const res = await fetch(`${BASE}/verifications/${id}`, { headers });
  if (!res.ok) throw new Error("Verification not found");
  return res.json();
}

export async function approveVerification(id: string, notes?: string): Promise<void> {
  await fetch(`${BASE}/verifications/${id}/approve`, {
    method: "POST",
    headers,
    body: JSON.stringify({ notes }),
  });
}

export async function rejectVerification(id: string, reason: string, fraud_flag = false): Promise<void> {
  await fetch(`${BASE}/verifications/${id}/reject`, {
    method: "POST",
    headers,
    body: JSON.stringify({ reason, fraud_flag }),
  });
}

export async function fetchFrames(id: string): Promise<string[]> {
  const res = await fetch(`${BASE}/verifications/${id}/frames`, { headers });
  if (!res.ok) return [];
  const data = await res.json();
  return data.urls ?? [];
}

export async function fetchStats(): Promise<AdminStats> {
  const res = await fetch(`${BASE}/stats`, { headers });
  if (!res.ok) throw new Error("Failed to fetch stats");
  return res.json();
}

export async function fetchWebhooks(id: string): Promise<WebhookDelivery[]> {
  const res = await fetch(`${BASE}/webhooks/${id}`, { headers });
  if (!res.ok) return [];
  return res.json();
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
  if (!res.ok) {
    const error = await res.text();
    throw new Error(error || "Failed to create verification");
  }
  return res.json();
}
