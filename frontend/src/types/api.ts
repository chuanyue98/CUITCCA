export interface QueryResponse {
  answer: string;
  source_nodes?: Array<{
    text: string;
    node_id?: string;
    doc_id?: string;
  }>;
}

export interface UploadResponse {
  status: string;
  message?: string;
}

export interface FeedbackRequest {
  email: string;
  message: string;
}

export interface IndexListResponse {
  indexes: string[];
}

export interface StatsResponse {
  total_visits: number;
  user_visits: Record<string, number>;
  endpoint_visits: Record<string, number>;
  ip_count: number;
}
