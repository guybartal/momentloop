import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { toast } from "sonner";
import type { Project, Video, Export } from "../types";
import api from "../services/api";
import ExportProgressStepper from "../components/export/ExportProgressStepper";

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

function TrashIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
    </svg>
  );
}

export default function ExportPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [videos, setVideos] = useState<Video[]>([]);
  const [currentExport, setCurrentExport] = useState<Export | null>(null);
  const [exportHistory, setExportHistory] = useState<Export[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isExporting, setIsExporting] = useState(false);
  const [regeneratingVideos, setRegeneratingVideos] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (projectId) {
      loadData();
    }
  }, [projectId]);

  // Poll for export status if pending or processing
  useEffect(() => {
    if (!currentExport || (currentExport.status !== "pending" && currentExport.status !== "processing")) {
      setIsExporting(false);
      return;
    }

    const interval = setInterval(async () => {
      try {
        const response = await api.get<Export>(`/exports/${currentExport.id}`);
        setCurrentExport(response.data);
        if (response.data.status === "ready" || response.data.status === "failed") {
          // Refresh export history
          loadExportHistory();
          toast.success(response.data.status === "ready" ? "Export completed!" : "Export failed");
          clearInterval(interval);
        }
      } catch (error) {
        console.error("Failed to check export status:", error);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [currentExport?.id, currentExport?.status]);

  const loadData = async () => {
    try {
      const [projectRes, videosRes] = await Promise.all([
        api.get<Project>(`/projects/${projectId}`),
        api.get<Video[]>(`/projects/${projectId}/videos`),
      ]);
      setProject(projectRes.data);
      setVideos(videosRes.data);
      await loadExportHistory();
    } catch (error) {
      console.error("Failed to load data:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const loadExportHistory = async () => {
    try {
      const response = await api.get<Export[]>(`/projects/${projectId}/exports`);
      setExportHistory(response.data);
      // Set the most recent export as current if it's processing
      const processing = response.data.find(e => e.status === "pending" || e.status === "processing");
      if (processing) {
        setCurrentExport(processing);
        setIsExporting(true);
      }
    } catch (error) {
      console.error("Failed to load export history:", error);
    }
  };

  const startExport = async () => {
    if (!projectId) return;

    setIsExporting(true);
    try {
      const response = await api.post<Export>(`/projects/${projectId}/export`, {
        include_transitions: true,
      });
      setCurrentExport(response.data);
      toast.success("Export started");
    } catch (error) {
      console.error("Failed to start export:", error);
      toast.error("Failed to start export");
      setIsExporting(false);
    }
  };

  const deleteExport = async (exportId: string) => {
    try {
      await api.delete(`/exports/${exportId}`);
      setExportHistory((prev) => prev.filter((e) => e.id !== exportId));
      if (currentExport?.id === exportId) {
        setCurrentExport(null);
      }
      toast.success("Export deleted");
    } catch (error) {
      console.error("Failed to delete export:", error);
      toast.error("Failed to delete export");
    }
  };

  const regenerateVideo = async (videoId: string) => {
    const video = videos.find((v) => v.id === videoId);
    if (!video) return;

    setRegeneratingVideos((prev) => ({ ...prev, [videoId]: true }));
    try {
      // Get the photo's animation prompt
      const photoRes = await api.get(`/photos/${video.photo_id}`);
      const photo = photoRes.data;

      if (!photo.styled_url || !photo.animation_prompt) {
        toast.error("Photo needs to be styled and have an animation prompt");
        return;
      }

      // Generate new video
      await api.post(`/photos/${video.photo_id}/generate-video`, {
        prompt: photo.animation_prompt,
      });
      toast.success("Video regeneration started");
      // Reload videos to get updated status
      const videosRes = await api.get<Video[]>(`/projects/${projectId}/videos`);
      setVideos(videosRes.data);
    } catch (error) {
      console.error("Failed to regenerate video:", error);
      toast.error("Failed to regenerate video");
    } finally {
      setRegeneratingVideos((prev) => ({ ...prev, [videoId]: false }));
    }
  };

  const readyVideos = videos.filter((v) => v.status === "ready");
  const isProcessing = currentExport?.status === "pending" || currentExport?.status === "processing";
  const latestReadyExport = exportHistory.find((e) => e.status === "ready");

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-500 mb-4">Project not found</p>
          <Link to="/" className="text-primary-600 hover:text-primary-700">
            Back to dashboard
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex justify-between items-center">
          <div className="flex items-center gap-4">
            <Link
              to={`/projects/${projectId}`}
              className="text-gray-600 hover:text-gray-900"
            >
              &larr; Back to project
            </Link>
            <h1 className="text-xl font-bold text-gray-900">Export Video</h1>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Current Export / Video Preview Section */}
        <div className="bg-white rounded-xl shadow-sm p-8 mb-8">
          <h2 className="text-lg font-semibold text-gray-900 mb-6 flex items-center gap-2">
            <FilmIcon className="w-5 h-5 text-primary-600" />
            Video Export
          </h2>

          {/* Video Preview or Progress */}
          <div className="aspect-video bg-gray-900 rounded-lg mb-8 flex items-center justify-center overflow-hidden">
            {isProcessing && currentExport ? (
              <div className="w-full p-8">
                <ExportProgressStepper
                  currentStep={currentExport.progress_step}
                  detail={currentExport.progress_detail}
                  percent={currentExport.progress_percent}
                />
              </div>
            ) : latestReadyExport?.file_url ? (
              <video
                controls
                className="w-full h-full"
                src={`${API_URL}${latestReadyExport.file_url}`}
                poster={latestReadyExport.thumbnail_url ? `${API_URL}${latestReadyExport.thumbnail_url}` : undefined}
              />
            ) : (
              <div className="text-center text-gray-400">
                <PlayIcon className="w-16 h-16 mx-auto mb-4" />
                <p>Video preview will appear here</p>
              </div>
            )}
          </div>

          {/* Video Stats */}
          <div className="grid grid-cols-3 gap-4 mb-8">
            <div className="bg-gray-50 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-gray-900">
                {readyVideos.length}
              </div>
              <div className="text-sm text-gray-500">Ready Videos</div>
            </div>
            <div className="bg-gray-50 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-gray-900">
                {videos.filter((v) => v.video_type === "scene").length}
              </div>
              <div className="text-sm text-gray-500">Scenes</div>
            </div>
            <div className="bg-gray-50 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-gray-900">
                {videos.filter((v) => v.video_type === "transition").length}
              </div>
              <div className="text-sm text-gray-500">Transitions</div>
            </div>
          </div>

          {/* Export Controls */}
          <div className="text-center">
            {readyVideos.length === 0 ? (
              <div className="text-gray-500">
                <p className="mb-2">No videos ready to export</p>
                <Link
                  to={`/projects/${projectId}`}
                  className="text-primary-600 hover:text-primary-700"
                >
                  Go back and generate some videos
                </Link>
              </div>
            ) : isProcessing ? (
              <div className="text-gray-500">
                <p className="font-medium">Export in progress...</p>
              </div>
            ) : latestReadyExport ? (
              <div className="flex items-center justify-center gap-4">
                <a
                  href={`${API_URL}${latestReadyExport.file_url}`}
                  download={`export-${latestReadyExport.id}.mp4`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 px-6 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
                >
                  <DownloadIcon className="w-4 h-4" />
                  Download Video
                </a>
                <button
                  onClick={startExport}
                  disabled={isExporting}
                  className="inline-flex items-center gap-2 px-6 py-3 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50"
                >
                  <RefreshIcon className={`w-4 h-4 ${isExporting ? "animate-spin" : ""}`} />
                  Re-export
                </button>
              </div>
            ) : (
              <button
                onClick={startExport}
                disabled={isExporting}
                className="px-8 py-3 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50"
              >
                {isExporting ? "Starting..." : "Generate Final Video"}
              </button>
            )}
          </div>
        </div>

        {/* Video List with Regenerate */}
        {videos.length > 0 && (
          <div className="bg-white rounded-xl shadow-sm p-6 mb-8">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              Videos in Export
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              Regenerate individual videos and then re-export to update the final video.
            </p>
            <div className="space-y-2">
              {videos
                .filter((v) => v.video_type === "scene")
                .sort((a, b) => (a.position || 0) - (b.position || 0))
                .map((video, index) => (
                  <div
                    key={video.id}
                    className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
                  >
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <span className="text-gray-400 text-sm w-6">
                        {index + 1}.
                      </span>
                      {video.file_url && video.status === "ready" && (
                        <video
                          src={`${API_URL}${video.file_url}`}
                          className="w-16 h-10 object-cover rounded"
                        />
                      )}
                      <span className="capitalize text-sm">{video.video_type}</span>
                      {video.prompt && (
                        <span className="text-sm text-gray-500 truncate max-w-xs">
                          {video.prompt}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <span
                        className={`px-2 py-1 text-xs rounded-full ${
                          video.status === "ready"
                            ? "bg-green-100 text-green-700"
                            : video.status === "generating"
                            ? "bg-yellow-100 text-yellow-700"
                            : video.status === "failed"
                            ? "bg-red-100 text-red-700"
                            : "bg-gray-100 text-gray-700"
                        }`}
                      >
                        {video.status}
                      </span>
                      <button
                        onClick={() => regenerateVideo(video.id)}
                        disabled={regeneratingVideos[video.id] || video.status === "generating"}
                        className="p-2 text-gray-500 hover:text-primary-600 hover:bg-gray-100 rounded transition-colors disabled:opacity-50"
                        title="Regenerate video"
                      >
                        <RefreshIcon className={`w-4 h-4 ${regeneratingVideos[video.id] ? "animate-spin" : ""}`} />
                      </button>
                    </div>
                  </div>
                ))}
            </div>
          </div>
        )}

        {/* Export History */}
        {exportHistory.length > 0 && (
          <div className="bg-white rounded-xl shadow-sm p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              Export History
            </h2>
            <div className="space-y-3">
              {exportHistory.map((exp) => (
                <div
                  key={exp.id}
                  className="flex items-center justify-between p-4 bg-gray-50 rounded-lg"
                >
                  <div className="flex items-center gap-4">
                    {/* Thumbnail */}
                    <div className="w-20 h-12 bg-gray-200 rounded overflow-hidden flex-shrink-0">
                      {exp.thumbnail_url ? (
                        <img
                          src={`${API_URL}${exp.thumbnail_url}`}
                          alt="Export thumbnail"
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center">
                          <FilmIcon className="w-6 h-6 text-gray-400" />
                        </div>
                      )}
                    </div>
                    <div>
                      <div className="text-sm font-medium text-gray-900">
                        {new Date(exp.created_at).toLocaleString()}
                      </div>
                      <div className="flex items-center gap-2 mt-1">
                        <span
                          className={`px-2 py-0.5 text-xs rounded-full ${
                            exp.status === "ready"
                              ? "bg-green-100 text-green-700"
                              : exp.status === "processing" || exp.status === "pending"
                              ? "bg-yellow-100 text-yellow-700"
                              : "bg-red-100 text-red-700"
                          }`}
                        >
                          {exp.status}
                        </span>
                        {exp.error_message && (
                          <span className="text-xs text-red-500">{exp.error_message}</span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {exp.status === "ready" && exp.file_url && (
                      <a
                        href={`${API_URL}${exp.file_url}`}
                        download={`export-${exp.id}.mp4`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="p-2 text-gray-500 hover:text-green-600 hover:bg-gray-100 rounded transition-colors"
                        title="Download"
                      >
                        <DownloadIcon className="w-4 h-4" />
                      </a>
                    )}
                    <button
                      onClick={() => deleteExport(exp.id)}
                      className="p-2 text-gray-500 hover:text-red-600 hover:bg-gray-100 rounded transition-colors"
                      title="Delete export"
                    >
                      <TrashIcon className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
