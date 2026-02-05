import type { Video as VideoType } from "../../types";

interface VideoPreviewProps {
  video: VideoType;
  apiUrl: string;
  onRegenerate?: () => void;
}

export default function VideoPreview({
  video,
  apiUrl,
  onRegenerate,
}: VideoPreviewProps) {
  const videoUrl = video.video_url ? `${apiUrl}${video.video_url}` : null;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm overflow-hidden">
      <div className="aspect-video bg-gray-900 flex items-center justify-center">
        {video.status === "ready" && videoUrl ? (
          <video
            controls
            className="w-full h-full"
            src={videoUrl}
            poster={undefined}
          />
        ) : video.status === "generating" ? (
          <div className="text-center text-white">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white mx-auto mb-2"></div>
            <p className="text-sm">Generating video...</p>
          </div>
        ) : video.status === "failed" ? (
          <div className="text-center text-red-400">
            <svg
              className="mx-auto h-8 w-8 mb-2"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
            <p className="text-sm">Generation failed</p>
          </div>
        ) : (
          <div className="text-center text-gray-400">
            <svg
              className="mx-auto h-8 w-8 mb-2"
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
            </svg>
            <p className="text-sm">Pending</p>
          </div>
        )}
      </div>
      <div className="p-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium capitalize text-gray-900 dark:text-gray-100">
            {video.video_type}
          </span>
          <span
            className={`px-2 py-0.5 text-xs rounded-full ${
              video.status === "ready"
                ? "bg-green-100 dark:bg-green-900/50 text-green-700 dark:text-green-300"
                : video.status === "generating"
                ? "bg-yellow-100 dark:bg-yellow-900/50 text-yellow-700 dark:text-yellow-300"
                : video.status === "failed"
                ? "bg-red-100 dark:bg-red-900/50 text-red-700 dark:text-red-300"
                : "bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300"
            }`}
          >
            {video.status}
          </span>
        </div>
        {video.prompt && (
          <p className="text-xs text-gray-500 dark:text-gray-400 line-clamp-2">{video.prompt}</p>
        )}
        {onRegenerate && video.status !== "generating" && (
          <button
            onClick={onRegenerate}
            className="mt-2 text-xs text-primary-600 hover:text-primary-700"
          >
            Regenerate
          </button>
        )}
      </div>
    </div>
  );
}
