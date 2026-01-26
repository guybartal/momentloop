import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
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
              ? "border-primary-500 bg-primary-50"
              : "border-gray-300 bg-white hover:border-gray-400"
          } ${isUploading ? "opacity-50 cursor-not-allowed" : ""}`}
        >
          <input {...getInputProps()} />
          {isUploading ? (
            <div>
              <div className="w-full bg-gray-200 rounded-full h-2 mb-2">
                <div
                  className="bg-primary-600 h-2 rounded-full transition-all"
                  style={{ width: `${uploadProgress}%` }}
                ></div>
              </div>
              <p className="text-gray-600">Uploading... {uploadProgress}%</p>
            </div>
          ) : isDragActive ? (
            <p className="text-primary-600">Drop the images here...</p>
          ) : (
            <div>
              <svg
                className="mx-auto h-12 w-12 text-gray-400"
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
              <p className="text-gray-600 mt-2">
                Drag and drop photos here, or click to browse
              </p>
              <p className="text-sm text-gray-400 mt-1">
                JPG, PNG, GIF, WEBP up to 10MB
              </p>
            </div>
          )}
        </div>

        {/* Google Photos import button */}
        <button
          onClick={() => setShowGooglePhotosPicker(true)}
          disabled={isUploading}
          className={`w-full flex items-center justify-center gap-2 px-4 py-3 border border-gray-300 rounded-xl bg-white hover:bg-gray-50 transition-colors ${
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
          <span className="text-gray-700">Import from Google Photos</span>
        </button>
      </div>

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
