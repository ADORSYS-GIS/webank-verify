export interface VerificationListItem {
  id: string;
  user_id: string;
  status: "pending" | "approved" | "rejected" | "manual_review";
  doc_type: string | null;
  country: string;
  risk_score: number | null;
  warning_count: number;
  created_at: string;
}

export interface Warning {
  code: string;
  message: string;
  severity: "info" | "warning" | "critical";
}

export interface DocumentFields {
  type: string;
  first_name: string | null;
  last_name: string | null;
  date_of_birth: string | null;
  birth_place: string | null;
  document_number: string | null;
  expiry_date: string | null;
  is_expired: boolean;
  age: number | null;
  is_underage: boolean;
  confidence: number;
}

export interface LivenessMetrics {
  score: number;
  face_quality: number;
  face_occlusion: number;
  face_luminance: number;
  frames_analyzed: number;
  passed: boolean;
}

export interface FaceMatchResult {
  similarity: number;
  passed: boolean;
  distance: number;
  model: string;
  threshold_used: number;
}

export interface IPAnalysis {
  ip: string;
  country: string | null;
  country_name: string | null;
  city: string | null;
  isp: string | null;
  is_vpn: boolean;
  is_proxy: boolean;
  is_tor: boolean;
  risk_score: number;
  risk_flags: string[];
}

export interface VerificationDetail {
  id: string;
  user_id: string;
  type: string;
  status: string;
  doc_type: string | null;
  country: string;
  risk_score: number | null;
  warnings: Warning[];
  document: DocumentFields | null;
  liveness: LivenessMetrics | null;
  face_match: FaceMatchResult | null;
  ip_intelligence: IPAnalysis | null;
  device_info: Record<string, string> | null;
  reviewer: string | null;
  review_notes: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminStats {
  total: number;
  pending: number;
  approved: number;
  rejected: number;
  manual_review: number;
  approved_today: number;
  rejected_today: number;
}

export interface WebhookDelivery {
  id: string;
  event_type: string;
  target_url: string | null;
  http_status: number | null;
  attempt: number;
  delivered_at: string;
}
