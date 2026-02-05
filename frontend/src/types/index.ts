export interface User {
  id: string;
  email: string;
  name: string | null;
  avatar_url: string | null;
}

export interface Project {
  id: string;
  name: string;
  style: StyleType | null;
  style_prompt: string | null;
  status: "draft" | "processing" | "complete";
  thumbnail_url: string | null;
  created_at: string;
  updated_at: string;
  photos?: Photo[];
  videos?: Video[];
}

export type StyleType = "ghibli" | "lego" | "minecraft" | "simpsons";

export interface Photo {
  id: string;
  project_id: string;
  original_path: string;
  original_url: string;
  styled_path: string | null;
  styled_url: string | null;
  animation_prompt: string | null;
  prompt_generation_status: "pending" | "generating" | "completed" | "failed";
  position: number;
  status: "uploaded" | "styling" | "styled" | "ready";
  created_at: string;
}

export interface StyledVariant {
  id: string;
  styled_url: string;
  style: string;
  is_selected: boolean;
  created_at: string;
}

export interface Video {
  id: string;
  photo_id: string | null;
  project_id: string;
  video_path: string | null;
  video_url: string | null;
  video_type: "scene" | "transition";
  source_photo_id: string | null;
  target_photo_id: string | null;
  prompt: string | null;
  duration_seconds: number | null;
  position: number | null;
  status: "pending" | "generating" | "ready" | "failed";
  is_selected: boolean;
  created_at: string;
}

export interface Export {
  id: string;
  project_id: string;
  file_path: string | null;
  file_url: string | null;
  thumbnail_path: string | null;
  thumbnail_url: string | null;
  status: "pending" | "processing" | "ready" | "failed";
  progress_step: string | null;
  progress_detail: string | null;
  progress_percent: number;
  error_message: string | null;
  created_at: string;
}

export interface ExportStatus {
  export_id: string;
  status: "pending" | "processing" | "ready" | "failed";
  file_url: string | null;
  thumbnail_url: string | null;
  progress: number;
  progress_step: string | null;
  progress_detail: string | null;
  error_message: string | null;
}
