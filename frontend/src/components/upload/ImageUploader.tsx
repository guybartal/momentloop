import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { toast } from "sonner";
import api from "../../services/api";
import type { Photo } from "../../types";
import GooglePhotosPicker from "./GooglePhotosPicker";

interface ImageUploaderProps {
  projectId: string;
  onUploadComplete: (photos: Photo[]) => void;
  onPhotosImported?: () => void;
}

export default function ImageUploader({
  projectId,
  onUploadComplete,
  onPhotosImported,
}: ImageUploaderProps) {
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [showGooglePhotosPicker, setShowGooglePhotosPicker] = useState(false);
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const [generatePrompt, setGeneratePrompt] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      if (acceptedFiles.length === 0) return;

      setIsUploading(true);
      setUploadProgress(0);

      const formData = new FormData();
      acceptedFiles.forEach((file) => {
        formData.append("files", file);
      });

      try {
        const response = await api.post<Photo[]>(
          `/projects/${projectId}/photos`,
          formData,
          {
            headers: {
              "Content-Type": "multipart/form-data",
            },
            onUploadProgress: (progressEvent) => {
              const progress = progressEvent.total
                ? Math.round((progressEvent.loaded * 100) / progressEvent.total)
                : 0;
              setUploadProgress(progress);
            },
          }
        );
        onUploadComplete(response.data);
      } catch (error) {
        console.error("Upload failed:", error);
      } finally {
        setIsUploading(false);
        setUploadProgress(0);
      }
    },
    [projectId, onUploadComplete]
  );

  const handleGooglePhotosImportComplete = useCallback(() => {
    // Trigger a full reload of photos in the parent component
    if (onPhotosImported) {
      onPhotosImported();
    }
  }, [onPhotosImported]);

  const handleGenerateImage = async () => {
    if (!generatePrompt.trim()) return;

    setIsGenerating(true);
    try {
      const response = await api.post<Photo>(
        `/projects/${projectId}/generate-image`,
        {
          prompt: generatePrompt.trim(),
          aspect_ratio: "16:9",
        }
      );
      onUploadComplete([response.data]);
      toast.success("Image generated successfully");
      setShowGenerateModal(false);
      setGeneratePrompt("");
    } catch (error) {
      console.error("Image generation failed:", error);
      toast.error("Failed to generate image");
    } finally {
      setIsGenerating(false);
    }
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "image/jpeg": [".jpg", ".jpeg"],
      "image/png": [".png"],
      "image/gif": [".gif"],
      "image/webp": [".webp"],
    },
    maxSize: 10 * 1024 * 1024, // 10MB
    disabled: isUploading,
  });

  return (
    <>
      <div className="space-y-3">
        {/* Drag and drop zone */}
        <div
          {...getRootProps()}
          className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
            isDragActive
              ? "border-primary-500 bg-primary-50 dark:bg-primary-900/20"
              : "border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 hover:border-gray-400 dark:hover:border-gray-500"
          } ${isUploading ? "opacity-50 cursor-not-allowed" : ""}`}
        >
          <input {...getInputProps()} />
          {isUploading ? (
            <div>
              <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 mb-2">
                <div
                  className="bg-primary-600 h-2 rounded-full transition-all"
                  style={{ width: `${uploadProgress}%` }}
                ></div>
              </div>
              <p className="text-gray-600 dark:text-gray-400">Uploading... {uploadProgress}%</p>
            </div>
          ) : isDragActive ? (
            <p className="text-primary-600">Drop the images here...</p>
          ) : (
            <div>
              <svg
                className="mx-auto h-12 w-12 text-gray-400 dark:text-gray-500"
                stroke="currentColor"
                fill="none"
                viewBox="0 0 48 48"
              >
                <path
                  d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
                  strokeWidth={2}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <p className="text-gray-600 dark:text-gray-400 mt-2">
                Drag and drop photos here, or click to browse
              </p>
              <p className="text-sm text-gray-400 dark:text-gray-500 mt-1">
                JPG, PNG, GIF, WEBP up to 10MB
              </p>
            </div>
          )}
        </div>

        {/* Action buttons row */}
        <div className="grid grid-cols-2 gap-3">
          {/* Generate with AI button */}
          <button
            onClick={() => setShowGenerateModal(true)}
            disabled={isUploading || isGenerating}
            className={`flex items-center justify-center gap-2 px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-xl bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors ${
              isUploading || isGenerating ? "opacity-50 cursor-not-allowed" : ""
            }`}
          >
            <svg
              className="w-5 h-5 text-purple-500"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
              />
            </svg>
            <span className="text-gray-700 dark:text-gray-300">Generate with AI</span>
          </button>

          {/* Google Photos import button */}
          <button
            onClick={() => setShowGooglePhotosPicker(true)}
            disabled={isUploading}
            className={`flex items-center justify-center gap-2 px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-xl bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors ${
              isUploading ? "opacity-50 cursor-not-allowed" : ""
            }`}
          >
            <svg
              className="w-5 h-5"
              viewBox="0 0 24 24"
              fill="none"
            >
              <circle cx="12" cy="12" r="10" stroke="#EA4335" strokeWidth="2" />
              <path
                d="M12 7v5l3.5 3.5"
                stroke="#4285F4"
                strokeWidth="2"
                strokeLinecap="round"
              />
              <path d="M8 11h8" stroke="#34A853" strokeWidth="2" strokeLinecap="round" />
              <path d="M12 8v8" stroke="#FBBC05" strokeWidth="2" strokeLinecap="round" />
            </svg>
            <span className="text-gray-700 dark:text-gray-300">Google Photos</span>
          </button>
        </div>
      </div>

      {/* Generate Image Modal */}
      {showGenerateModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl p-6 max-w-lg w-full mx-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                Generate Image with AI
              </h3>
              <button
                onClick={() => {
                  setShowGenerateModal(false);
                  setGeneratePrompt("");
                }}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
              Describe the image you want to create. Be detailed for best results.
            </p>
            <textarea
              value={generatePrompt}
              onChange={(e) => setGeneratePrompt(e.target.value)}
              placeholder="e.g., A serene mountain landscape at sunset with golden light reflecting off a calm lake..."
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
              rows={4}
              autoFocus
              disabled={isGenerating}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && generatePrompt.trim()) {
                  handleGenerateImage();
                }
              }}
            />
            <div className="flex justify-between items-center mt-4">
              <p className="text-xs text-gray-400 dark:text-gray-500">
                Ctrl+Enter to generate
              </p>
              <div className="flex gap-3">
                <button
                  onClick={() => {
                    setShowGenerateModal(false);
                    setGeneratePrompt("");
                  }}
                  disabled={isGenerating}
                  className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleGenerateImage}
                  disabled={!generatePrompt.trim() || isGenerating}
                  className={`px-4 py-2 rounded-lg font-medium text-white transition-colors ${
                    !generatePrompt.trim() || isGenerating
                      ? "bg-gray-400 dark:bg-gray-600 cursor-not-allowed"
                      : "bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700"
                  }`}
                >
                  {isGenerating ? (
                    <span className="flex items-center gap-2">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                      Generating...
                    </span>
                  ) : (
                    "Generate"
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Google Photos Picker Modal */}
      {showGooglePhotosPicker && (
        <GooglePhotosPicker
          projectId={projectId}
          onClose={() => setShowGooglePhotosPicker(false)}
          onImportComplete={handleGooglePhotosImportComplete}
        />
      )}
    </>
  );
}
