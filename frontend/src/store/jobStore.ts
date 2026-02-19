import { create } from "zustand";
import api from "../services/api";

export type JobType = "style_transfer" | "prompt_generation" | "video_generation" | "export";

export type JobStatus = "running" | "completed" | "failed";

export interface Job {
  id: string;
  type: JobType;
  description: string;
  status: JobStatus;
  createdAt: number;
  startedAt: number | null;
  completedAt: number | null;
  projectId: string;
  projectName?: string;
  error?: string;
}

interface ApiJob {
  id: string;
  user_id: string;
  project_id: string;
  job_type: JobType;
  description: string;
  status: JobStatus;
  error: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

function apiJobToLocal(apiJob: ApiJob): Job {
  return {
    id: apiJob.id,
    type: apiJob.job_type,
    description: apiJob.description,
    status: apiJob.status,
    createdAt: new Date(apiJob.created_at).getTime(),
    startedAt: apiJob.started_at ? new Date(apiJob.started_at).getTime() : null,
    completedAt: apiJob.completed_at ? new Date(apiJob.completed_at).getTime() : null,
    projectId: apiJob.project_id,
    error: apiJob.error ?? undefined,
  };
}

interface JobState {
  jobs: Job[];
  initialized: boolean;
  loadJobs: () => Promise<void>;
  addJob: (job: Omit<Job, "id" | "createdAt" | "startedAt" | "completedAt" | "status">) => string;
  completeJob: (id: string) => void;
  failJob: (id: string, error?: string) => void;
  clearNotifications: () => void;
  clearNotification: (id: string) => void;
  getActiveJobs: () => Job[];
  getNotifications: () => Job[];
  getUnreadCount: () => number;
}

export const useJobStore = create<JobState>((set, get) => ({
  jobs: [],
  initialized: false,

  loadJobs: async () => {
    try {
      const response = await api.get<ApiJob[]>("/jobs?limit=50");
      const jobs = response.data.map((j: ApiJob) => apiJobToLocal(j));
      set({ jobs, initialized: true });
    } catch (error) {
      console.error("Failed to load jobs:", error);
      set({ initialized: true });
    }
  },

  addJob: (jobData) => {
    const tempId = crypto.randomUUID();
    const job: Job = {
      ...jobData,
      id: tempId,
      status: "running",
      createdAt: Date.now(),
      startedAt: Date.now(),
      completedAt: null,
    };
    set((state) => ({ jobs: [job, ...state.jobs] }));

    // Persist to API (non-blocking), replace temp ID with server ID
    api
      .post<ApiJob>("/jobs", {
        project_id: jobData.projectId,
        job_type: jobData.type,
        description: jobData.description,
      })
      .then((response: { data: ApiJob }) => {
        const serverJob = apiJobToLocal(response.data);
        serverJob.projectName = jobData.projectName;
        set((state: JobState) => ({
          jobs: state.jobs.map((j: Job) => (j.id === tempId ? { ...serverJob, status: j.status, completedAt: j.completedAt, error: j.error } : j)),
        }));
      })
      .catch(() => {
        console.error("Failed to persist job");
      });

    return tempId;
  },

  completeJob: (id) => {
    set((state) => ({
      jobs: state.jobs.map((j) =>
        j.id === id ? { ...j, status: "completed" as const, completedAt: Date.now() } : j
      ),
    }));
    api.patch(`/jobs/${id}/complete`).catch(() => {
      console.error("Failed to persist job completion");
    });
  },

  failJob: (id, error) => {
    set((state) => ({
      jobs: state.jobs.map((j) =>
        j.id === id
          ? { ...j, status: "failed" as const, completedAt: Date.now(), error }
          : j
      ),
    }));
    api
      .patch(`/jobs/${id}/fail${error ? `?error=${encodeURIComponent(error)}` : ""}`)
      .catch(() => {
        console.error("Failed to persist job failure");
      });
  },

  clearNotifications: () => {
    set((state) => ({
      jobs: state.jobs.filter((j) => j.status === "running"),
    }));
    api.delete("/jobs/notifications").catch(() => {
      console.error("Failed to clear notifications");
    });
  },

  clearNotification: (id) => {
    set((state) => ({
      jobs: state.jobs.filter((j) => j.id !== id || j.status === "running"),
    }));
    api.delete(`/jobs/${id}`).catch(() => {
      console.error("Failed to clear notification");
    });
  },

  getActiveJobs: () => {
    return get().jobs.filter((j) => j.status === "running");
  },

  getNotifications: () => {
    return get().jobs.filter((j) => j.status === "completed" || j.status === "failed");
  },

  getUnreadCount: () => {
    return get().jobs.filter((j) => j.status === "completed" || j.status === "failed").length;
  },
}));
