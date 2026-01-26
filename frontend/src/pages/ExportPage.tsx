import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import type { Project, Video } from "../types";
import api from "../services/api";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

interface ExportData {
  id: string;
  project_id: string;
  file_path: string | null;
  file_url: string | null;
  status: "pending" | "processing" | "ready" | "failed";
  created_at: string;
}

export default function ExportPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [videos, setVideos] = useState<Video[]>([]);
  const [exportData, setExportData] = useState<ExportData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isExporting, setIsExporting] = useState(false);

  useEffect(() => {
    if (projectId) {
      loadData();
    }
  }, [projectId]);

  useEffect(() => {
    // Poll for export status if pending or processing
    if (
      exportData &&
      (exportData.status === "pending" || exportData.status === "processing")
    ) {
      const interval = setInterval(async () => {
        try {
          const response = await api.get<ExportData>(
            `/exports/${exportData.id}`
          );
          setExportData(response.data);
          if (
            response.data.status === "ready" ||
            response.data.status === "failed"
          ) {
            clearInterval(interval);
          }
        } catch (error) {
          console.error("Failed to check export status:", error);
        }
      }, 2000);

      return () => clearInterval(interval);
    }
  }, [exportData?.id, exportData?.status]);

  const loadData = async () => {
    try {
      const [projectRes, videosRes] = await Promise.all([
        api.get<Project>(`/projects/${projectId}`),
        api.get<Video[]>(`/projects/${projectId}/videos`),
      ]);
      setProject(projectRes.data);
      setVideos(videosRes.data);
    } catch (error) {
      console.error("Failed to load data:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const startExport = async () => {
    if (!projectId) return;

    setIsExporting(true);
    try {
      const response = await api.post<ExportData>(
        `/projects/${projectId}/export`
      );
      setExportData(response.data);
    } catch (error) {
      console.error("Failed to start export:", error);
    } finally {
      setIsExporting(false);
    }
  };

  const readyVideos = videos.filter((v) => v.status === "ready");

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
        <div className="bg-white rounded-xl shadow-sm p-8">
          {/* Video Preview */}
          <div className="aspect-video bg-gray-900 rounded-lg mb-8 flex items-center justify-center overflow-hidden">
            {exportData?.file_url && exportData.status === "ready" ? (
              <video
                controls
                className="w-full h-full"
                src={`${API_URL}${exportData.file_url}`}
              />
            ) : (
              <div className="text-center text-gray-400">
                <svg
                  className="mx-auto h-16 w-16 mb-4"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1}
                    d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"
                  />
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1}
                    d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
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
            ) : !exportData ? (
              <button
                onClick={startExport}
                disabled={isExporting}
                className="px-8 py-3 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50"
              >
                {isExporting ? "Starting..." : "Generate Final Video"}
              </button>
            ) : exportData.status === "ready" ? (
              <div className="space-y-4">
                <div className="text-green-600 font-medium">
                  Export complete!
                </div>
                <a
                  href={`${API_URL}/api/exports/${exportData.id}/download`}
                  download
                  className="inline-block px-8 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
                >
                  Download Video
                </a>
              </div>
            ) : exportData.status === "failed" ? (
              <div className="space-y-4">
                <div className="text-red-600 font-medium">Export failed</div>
                <button
                  onClick={startExport}
                  className="px-8 py-3 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
                >
                  Try Again
                </button>
              </div>
            ) : (
              <div className="text-gray-500">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600 mx-auto mb-4"></div>
                <p>
                  {exportData.status === "pending"
                    ? "Starting export..."
                    : "Processing your video..."}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Video List */}
        {videos.length > 0 && (
          <div className="mt-8 bg-white rounded-xl shadow-sm p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              Videos in Export
            </h2>
            <div className="space-y-2">
              {videos
                .sort((a, b) => (a.position || 0) - (b.position || 0))
                .map((video, index) => (
                  <div
                    key={video.id}
                    className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-gray-400 text-sm">
                        {index + 1}.
                      </span>
                      <span className="capitalize">{video.video_type}</span>
                      {video.prompt && (
                        <span className="text-sm text-gray-500 truncate max-w-xs">
                          {video.prompt}
                        </span>
                      )}
                    </div>
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
                  </div>
                ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
