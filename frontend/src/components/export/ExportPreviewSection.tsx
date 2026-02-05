import { Link } from "react-router-dom";

import ExportProgressStepper from "./ExportProgressStepper";
import type { Export } from "../../types";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

// Inline SVG icons
function FilmIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 4v16M17 4v16M3 8h4m10 0h4M3 12h18M3 16h4m10 0h4M4 20h16a1 1 0 001-1V5a1 1 0 00-1-1H4a1 1 0 00-1 1v14a1 1 0 001 1z" />
    </svg>
  );
}

function PlayIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

function DownloadIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
    </svg>
  );
}

function RefreshIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
    </svg>
  );
}

function StarIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="currentColor" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
    </svg>
  );
}

interface ExportPreviewSectionProps {
  projectId: string;
  mainExport: Export | null;
  latestExport: Export | null;
  currentExport: Export | null;
  isExporting: boolean;
  onExport: () => void;
}

export default function ExportPreviewSection({
  projectId,
  mainExport,
  latestExport,
  currentExport,
  isExporting,
  onExport,
}: ExportPreviewSectionProps) {
  // Priority: currentExport (if processing) > mainExport > latestExport
  const exportToShow = currentExport || mainExport || latestExport;
  const isProcessing = currentExport?.status === "processing" || currentExport?.status === "pending";
  const showingMainExport = !currentExport && mainExport && exportToShow?.id === mainExport.id;

  return (
    <section className="bg-white rounded-xl shadow-sm p-6 mb-8">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <FilmIcon className="w-5 h-5 text-primary-600" />
          <h2 className="text-lg font-semibold">Export Preview</h2>
        </div>
        <Link
          to={`/projects/${projectId}/export`}
          className="text-sm text-primary-600 hover:text-primary-700"
        >
          View All Exports
        </Link>
      </div>

      {/* Content based on state */}
      {isProcessing && currentExport ? (
        /* Export in progress */
        <div className="bg-gray-50 rounded-lg p-6">
          <ExportProgressStepper
            currentStep={currentExport.progress_step}
            detail={currentExport.progress_detail}
            percent={currentExport.progress_percent}
          />
        </div>
      ) : exportToShow?.status === "ready" && exportToShow.file_url ? (
        /* Ready export with video player */
        <div className="space-y-4">
          <div className="aspect-video bg-black rounded-lg overflow-hidden">
            <video
              src={`${API_URL}${exportToShow.file_url}`}
              controls
              className="w-full h-full"
              poster={exportToShow.thumbnail_url ? `${API_URL}${exportToShow.thumbnail_url}` : undefined}
            />
          </div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm text-gray-500">
              {showingMainExport && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs bg-yellow-100 text-yellow-800 rounded-full">
                  <StarIcon className="w-3 h-3" />
                  Main
                </span>
              )}
              Created {new Date(exportToShow.created_at).toLocaleDateString()}
            </div>
            <div className="flex items-center gap-3">
              <a
                href={`${API_URL}${exportToShow.file_url}`}
                download={`export-${exportToShow.id}.mp4`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 px-3 py-2 text-sm bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
              >
                <DownloadIcon className="w-4 h-4" />
                Download
              </a>
              <button
                onClick={onExport}
                disabled={isExporting}
                className="inline-flex items-center gap-2 px-4 py-2 text-sm bg-primary-600 text-white hover:bg-primary-700 rounded-lg transition-colors disabled:opacity-50"
              >
                <RefreshIcon className={`w-4 h-4 ${isExporting ? "animate-spin" : ""}`} />
                Re-export
              </button>
            </div>
          </div>
        </div>
      ) : exportToShow?.status === "failed" ? (
        /* Failed export */
        <div className="bg-red-50 rounded-lg p-6 text-center">
          <p className="text-red-600 mb-2">Export failed</p>
          {exportToShow.error_message && (
            <p className="text-sm text-red-500 mb-4">{exportToShow.error_message}</p>
          )}
          <button
            onClick={onExport}
            disabled={isExporting}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm bg-primary-600 text-white hover:bg-primary-700 rounded-lg transition-colors disabled:opacity-50"
          >
            <RefreshIcon className={`w-4 h-4 ${isExporting ? "animate-spin" : ""}`} />
            Try Again
          </button>
        </div>
      ) : (
        /* No export yet */
        <div className="bg-gray-50 rounded-lg p-8 text-center">
          <PlayIcon className="w-12 h-12 text-gray-400 mx-auto mb-4" />
          <p className="text-gray-600 mb-4">No export yet. Create your first video export!</p>
          <button
            onClick={onExport}
            disabled={isExporting}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white hover:bg-primary-700 rounded-lg transition-colors disabled:opacity-50"
          >
            <FilmIcon className="w-4 h-4" />
            Create Export
          </button>
        </div>
      )}
    </section>
  );
}
