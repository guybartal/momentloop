import { useState, useEffect, useRef } from "react";
import { useJobStore } from "../../store/jobStore";
import type { Job, JobType } from "../../store/jobStore";

function BellIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
      />
    </svg>
  );
}

function JobTypeIcon({ type, className }: { type: JobType; className?: string }) {
  switch (type) {
    case "style_transfer":
      return (
        <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01"
          />
        </svg>
      );
    case "prompt_generation":
      return (
        <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
          />
        </svg>
      );
    case "video_generation":
      return (
        <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
          />
        </svg>
      );
    case "export":
      return (
        <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M7 4v16M17 4v16M3 8h4m10 0h4M3 12h18M3 16h4m10 0h4M4 20h16a1 1 0 001-1V5a1 1 0 00-1-1H4a1 1 0 00-1 1v14a1 1 0 001 1z"
          />
        </svg>
      );
  }
}

function ElapsedTime({ since, until }: { since: number; until?: number }) {
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    if (until) return;
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, [until]);

  const elapsed = ((until || now) - since) / 1000;
  const minutes = Math.floor(elapsed / 60);
  const seconds = Math.floor(elapsed % 60);

  return (
    <span className="text-xs text-gray-400 dark:text-gray-500">
      {minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`}
    </span>
  );
}

function JobItem({ job, onDismiss }: { job: Job; onDismiss?: () => void }) {
  return (
    <div className="flex items-start gap-3 py-2 group">
      <div
        className={`mt-0.5 flex-shrink-0 p-1.5 rounded-lg ${
          job.status === "running"
            ? "bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400"
            : job.status === "completed"
              ? "bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400"
              : "bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400"
        }`}
      >
        <JobTypeIcon type={job.type} className="w-4 h-4" />
      </div>

      <div className="flex-1 min-w-0">
        <p className="text-sm text-gray-900 dark:text-gray-100 truncate">{job.description}</p>
        <div className="flex items-center gap-2 mt-0.5">
          {job.status === "running" ? (
            <>
              <span className="flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400">
                <span className="inline-block w-1.5 h-1.5 bg-blue-600 dark:bg-blue-400 rounded-full animate-pulse" />
                Running
              </span>
              <ElapsedTime since={job.createdAt} />
            </>
          ) : job.status === "completed" ? (
            <>
              <span className="text-xs text-green-600 dark:text-green-400">Completed</span>
              <ElapsedTime since={job.createdAt} until={job.completedAt!} />
            </>
          ) : (
            <>
              <span className="text-xs text-red-600 dark:text-red-400">Failed</span>
              {job.error && (
                <span className="text-xs text-gray-500 dark:text-gray-400 truncate">
                  {job.error}
                </span>
              )}
            </>
          )}
        </div>
      </div>

      {onDismiss && (
        <button
          onClick={onDismiss}
          className="opacity-0 group-hover:opacity-100 p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-opacity"
          aria-label="Dismiss notification"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>
      )}
    </div>
  );
}

export default function JobQueuePanel() {
  const [isOpen, setIsOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const { clearNotifications, clearNotification, loadJobs, initialized } = useJobStore();
  const jobs = useJobStore((s) => s.jobs);
  const notifications = useJobStore((s) => s.getNotifications());
  const totalCount = jobs.length;

  useEffect(() => {
    if (!initialized) {
      loadJobs();
    }
  }, [initialized, loadJobs]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className="relative" ref={panelRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative p-2 rounded-lg text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700 transition-colors"
        aria-label="Job queue and notifications"
      >
        <BellIcon className="w-5 h-5" />
        {totalCount > 0 && (
          <span className="absolute -top-1 -right-1 bg-primary-600 text-white text-xs rounded-full h-5 w-5 flex items-center justify-center font-medium">
            {totalCount > 9 ? "9+" : totalCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-96 bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 z-50 max-h-[70vh] overflow-hidden flex flex-col">
          <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
            <h3 className="font-semibold text-gray-900 dark:text-gray-100">Activity</h3>
            {notifications.length > 0 && (
              <button
                onClick={clearNotifications}
                className="text-xs text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300"
              >
                Clear All
              </button>
            )}
          </div>

          <div className="overflow-y-auto flex-1">
            {jobs.length > 0 ? (
              <div className="px-4 py-2">
                {jobs.map((job) => (
                  <JobItem
                    key={job.id}
                    job={job}
                    onDismiss={
                      job.status !== "running"
                        ? () => clearNotification(job.id)
                        : undefined
                    }
                  />
                ))}
              </div>
            ) : (
              <div className="px-4 py-8 text-center text-gray-400 dark:text-gray-500 text-sm">
                No active jobs or notifications
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
