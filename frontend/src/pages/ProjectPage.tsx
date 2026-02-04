import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import type { Project, Photo, StyleType, StyledVariant, Video } from "../types";
import api from "../services/api";
import ImageUploader from "../components/upload/ImageUploader";
import PhotoGallery from "../components/gallery/PhotoGallery";
import Lightbox from "../components/common/Lightbox";
import GeneratingTimer from "../components/common/GeneratingTimer";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const STYLES: { id: StyleType; label: string; icon: string }[] = [
  { id: "ghibli", label: "Ghibli", icon: "🏯" },
  { id: "lego", label: "Lego", icon: "🧱" },
  { id: "minecraft", label: "Minecraft", icon: "⛏️" },
  { id: "simpsons", label: "Simpsons", icon: "💛" },
];

// Debounce hook
function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]);

  return debouncedValue;
}

export default function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [selectedPhoto, setSelectedPhoto] = useState<Photo | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isApplyingStyle, setIsApplyingStyle] = useState(false);
  const [viewMode, setViewMode] = useState<"grid" | "compare">("grid");
  const [photoVariants, setPhotoVariants] = useState<Record<string, StyledVariant[]>>({});
  const [loadingVariants, setLoadingVariants] = useState<Record<string, boolean>>({});
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [photoVideos, setPhotoVideos] = useState<Record<string, Video[]>>({});
  const [generatingVideos, setGeneratingVideos] = useState<Record<string, boolean>>({});
  const [lightboxImage, setLightboxImage] = useState<{ url: string; alt: string } | null>(null);

  // Track animation prompt for debounced saving
  const [animationPrompt, setAnimationPrompt] = useState<string>("");
  const debouncedPrompt = useDebounce(animationPrompt, 1000);
  const lastSavedPromptRef = useRef<string>("");

  // Track style prompt for debounced saving
  const [stylePrompt, setStylePrompt] = useState<string>("");
  const debouncedStylePrompt = useDebounce(stylePrompt, 1000);
  const lastSavedStylePromptRef = useRef<string>("");
  const [showStylePrompt, setShowStylePrompt] = useState(false);

  useEffect(() => {
    if (projectId) {
      loadProject();
    }
  }, [projectId]);

  // Poll for style status when processing
  useEffect(() => {
    if (project?.status !== "processing") return;

    const interval = setInterval(async () => {
      try {
        const response = await api.get(`/projects/${projectId}/style-status`);
        const data = response.data;

        // Update photos with new statuses
        setPhotos((prev) =>
          prev.map((photo) => {
            const updated = data.photos.find(
              (p: { photo_id: string }) => p.photo_id === photo.id
            );
            if (updated) {
              return {
                ...photo,
                status: updated.status,
                styled_url: updated.styled_url,
              };
            }
            return photo;
          })
        );

        // Update project status if done
        if (data.project_status !== "processing") {
          setProject((prev) =>
            prev ? { ...prev, status: data.project_status } : prev
          );
          setIsApplyingStyle(false);
          // Reload full project to get final photo states
          loadProject();
        }
      } catch (error) {
        console.error("Failed to check style status:", error);
      }
    }, 5000); // Poll every 5 seconds instead of 2

    return () => clearInterval(interval);
  }, [project?.status, projectId]);

  // Auto-save animation prompt when it changes (debounced)
  useEffect(() => {
    if (
      selectedPhoto &&
      debouncedPrompt !== lastSavedPromptRef.current &&
      debouncedPrompt !== (selectedPhoto.animation_prompt || "")
    ) {
      // Only save if the prompt actually changed from what's in the database
      const savePrompt = async () => {
        try {
          await api.put(`/photos/${selectedPhoto.id}`, {
            animation_prompt: debouncedPrompt,
          });
          lastSavedPromptRef.current = debouncedPrompt;
          // Update the photos array too
          setPhotos((prev) =>
            prev.map((p) =>
              p.id === selectedPhoto.id
                ? { ...p, animation_prompt: debouncedPrompt }
                : p
            )
          );
        } catch (error) {
          console.error("Failed to save animation prompt:", error);
        }
      };
      savePrompt();
    }
  }, [debouncedPrompt, selectedPhoto]);

  // Sync animationPrompt state when selectedPhoto changes
  useEffect(() => {
    if (selectedPhoto) {
      setAnimationPrompt(selectedPhoto.animation_prompt || "");
      lastSavedPromptRef.current = selectedPhoto.animation_prompt || "";
    }
  }, [selectedPhoto?.id]);

  // Sync stylePrompt state when project changes
  useEffect(() => {
    if (project) {
      setStylePrompt(project.style_prompt || "");
      lastSavedStylePromptRef.current = project.style_prompt || "";
    }
  }, [project?.id]);

  // Auto-save style prompt when it changes (debounced)
  useEffect(() => {
    if (
      project &&
      debouncedStylePrompt !== lastSavedStylePromptRef.current
    ) {
      const saveStylePrompt = async () => {
        try {
          await api.put(`/projects/${project.id}`, {
            style_prompt: debouncedStylePrompt,
          });
          lastSavedStylePromptRef.current = debouncedStylePrompt;
          setProject((prev) =>
            prev ? { ...prev, style_prompt: debouncedStylePrompt } : prev
          );
        } catch (error) {
          console.error("Failed to save style prompt:", error);
        }
      };
      saveStylePrompt();
    }
  }, [debouncedStylePrompt, project?.id]);

  const loadProject = async () => {
    try {
      const [projectRes, photosRes, videosRes] = await Promise.all([
        api.get<Project>(`/projects/${projectId}`),
        api.get<{ items: Photo[]; total: number }>(`/projects/${projectId}/photos`),
        api.get<Video[]>(`/projects/${projectId}/videos`),
      ]);
      setProject(projectRes.data);
      setPhotos(photosRes.data.items);

      // Map videos to photos (group by photo_id)
      const videoMap: Record<string, Video[]> = {};
      videosRes.data.forEach((video: Video) => {
        if (video.photo_id && video.video_type === "scene") {
          if (!videoMap[video.photo_id]) {
            videoMap[video.photo_id] = [];
          }
          videoMap[video.photo_id].push(video);
        }
      });
      setPhotoVideos(videoMap);

      // Load variants for each photo
      photosRes.data.items.forEach((photo: Photo) => {
        if (photo.styled_url) {
          loadVariants(photo.id);
        }
      });
    } catch (error) {
      console.error("Failed to load project:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const loadVariants = async (photoId: string) => {
    try {
      const response = await api.get(`/photos/${photoId}/variants`);
      setPhotoVariants((prev) => ({
        ...prev,
        [photoId]: response.data.variants,
      }));
    } catch (error) {
      console.error("Failed to load variants:", error);
    }
  };

  const handleUploadComplete = useCallback((newPhotos: Photo[]) => {
    setPhotos((prev) => [...prev, ...newPhotos]);
  }, []);

  const handleReorder = useCallback(
    async (reorderedPhotos: Photo[]) => {
      setPhotos(reorderedPhotos);

      try {
        await api.put(`/projects/${projectId}/photos/reorder`, {
          photo_ids: reorderedPhotos.map((p) => p.id),
        });
      } catch (error) {
        console.error("Failed to save order:", error);
        loadProject();
      }
    },
    [projectId]
  );

  const handleDeletePhoto = async (photoId: string) => {
    try {
      await api.delete(`/photos/${photoId}`);
      setPhotos((prev) => prev.filter((p) => p.id !== photoId));
      if (selectedPhoto?.id === photoId) {
        setSelectedPhoto(null);
      }
      toast.success("Photo deleted");
    } catch (error) {
      toast.error("Failed to delete photo");
      console.error("Failed to delete photo:", error);
    }
  };

  const handleStyleSelect = async (style: StyleType) => {
    if (!project) return;

    // Update local state immediately for responsiveness
    setProject({ ...project, style });

    // Save to backend
    try {
      await api.put(`/projects/${projectId}`, { style });
    } catch (error) {
      console.error("Failed to save style:", error);
    }
  };

  const handleGenerateStyledImages = async () => {
    if (!project || !project.style || photos.length === 0) return;

    setIsApplyingStyle(true);

    try {
      await api.post(`/projects/${projectId}/stylize`, { style: project.style });
      setProject({ ...project, status: "processing" });
      toast.success("Style transfer started");
    } catch (error) {
      toast.error("Failed to apply style");
      console.error("Failed to apply style:", error);
      setIsApplyingStyle(false);
    }
  };

  const handleResetStuck = async () => {
    if (!projectId) return;

    try {
      const response = await api.post(`/projects/${projectId}/reset-stuck`);
      if (response.data.reset_count > 0) {
        // Reload project to get updated statuses
        await loadProject();
      }
      setIsApplyingStyle(false);
    } catch (error) {
      console.error("Failed to reset stuck photos:", error);
    }
  };

  const handleRegeneratePhoto = async (photoId: string) => {
    if (!project?.style) return;

    try {
      // Mark photo as styling
      setPhotos((prev) =>
        prev.map((p) => (p.id === photoId ? { ...p, status: "styling" as const } : p))
      );
      setLoadingVariants((prev) => ({ ...prev, [photoId]: true }));

      await api.post(`/photos/${photoId}/regenerate`, { style: project.style });

      // Poll for completion with longer interval
      const checkStatus = setInterval(async () => {
        try {
          const response = await api.get(`/photos/${photoId}`);
          const photo = response.data;
          if (photo.status !== "styling") {
            clearInterval(checkStatus);
            setPhotos((prev) =>
              prev.map((p) => (p.id === photoId ? photo : p))
            );
            // Update selectedPhoto if it's the one being regenerated
            setSelectedPhoto((prev) =>
              prev?.id === photoId ? photo : prev
            );
            setLoadingVariants((prev) => ({ ...prev, [photoId]: false }));
            // Reload variants
            loadVariants(photoId);
          }
        } catch {
          clearInterval(checkStatus);
          setLoadingVariants((prev) => ({ ...prev, [photoId]: false }));
        }
      }, 5000); // Poll every 5 seconds
    } catch (error) {
      console.error("Failed to regenerate photo:", error);
      setLoadingVariants((prev) => ({ ...prev, [photoId]: false }));
    }
  };

  const handleSelectVariant = async (photoId: string, variantId: string) => {
    try {
      const response = await api.post(`/photos/${photoId}/variants/select`, {
        variant_id: variantId,
      });

      // Update photo's styled_url
      setPhotos((prev) =>
        prev.map((p) =>
          p.id === photoId ? { ...p, styled_url: response.data.styled_url } : p
        )
      );
      // Update selectedPhoto if it's the one being updated
      setSelectedPhoto((prev) =>
        prev?.id === photoId ? { ...prev, styled_url: response.data.styled_url } : prev
      );

      // Update variants to reflect selection
      setPhotoVariants((prev) => ({
        ...prev,
        [photoId]: prev[photoId]?.map((v) => ({
          ...v,
          is_selected: v.id === variantId,
        })),
      }));
    } catch (error) {
      console.error("Failed to select variant:", error);
    }
  };

  const handleDeleteProject = async () => {
    try {
      await api.delete(`/projects/${projectId}`);
      toast.success("Project deleted");
      navigate("/");
    } catch (error) {
      toast.error("Failed to delete project");
      console.error("Failed to delete project:", error);
    }
  };

  const handleGenerateVideo = async (photoId: string) => {
    const photo = photos.find((p) => p.id === photoId);
    if (!photo?.styled_url) {
      toast.error("Photo must be styled first");
      return;
    }

    // Use current animationPrompt state if this is the selected photo, otherwise use saved prompt
    const promptToUse = selectedPhoto?.id === photoId ? animationPrompt : photo.animation_prompt;
    if (!promptToUse) {
      toast.error("Photo must have an animation prompt");
      return;
    }

    setGeneratingVideos((prev) => ({ ...prev, [photoId]: true }));

    try {
      // Pass the prompt explicitly to ensure we use the latest
      const response = await api.post<Video>(`/photos/${photoId}/generate-video`, {
        prompt: promptToUse,
      });

      // Add new video to the list
      setPhotoVideos((prev) => ({
        ...prev,
        [photoId]: [response.data, ...(prev[photoId] || []).map(v => ({ ...v, is_selected: false }))],
      }));

      // Poll for video completion
      const pollInterval = setInterval(async () => {
        try {
          const statusRes = await api.get(`/videos/${response.data.id}/status`);
          const status = statusRes.data;

          if (status.status === "ready" || status.status === "failed") {
            clearInterval(pollInterval);
            setGeneratingVideos((prev) => ({ ...prev, [photoId]: false }));

            // Reload all videos for this photo to get updated is_selected states
            const videosRes = await api.get<Video[]>(`/photos/${photoId}/videos`);
            setPhotoVideos((prev) => ({ ...prev, [photoId]: videosRes.data }));
          }
        } catch {
          clearInterval(pollInterval);
          setGeneratingVideos((prev) => ({ ...prev, [photoId]: false }));
        }
      }, 3000);
    } catch (error) {
      console.error("Failed to generate video:", error);
      setGeneratingVideos((prev) => ({ ...prev, [photoId]: false }));
    }
  };

  const handleSelectVideo = async (photoId: string, videoId: string) => {
    try {
      await api.post(`/photos/${photoId}/videos/select`, { video_id: videoId });

      // Update local state
      setPhotoVideos((prev) => ({
        ...prev,
        [photoId]: (prev[photoId] || []).map((v) => ({
          ...v,
          is_selected: v.id === videoId,
        })),
      }));
    } catch (error) {
      console.error("Failed to select video:", error);
    }
  };

  // Helper to get selected video for a photo
  const getSelectedVideo = (photoId: string): Video | undefined => {
    const videos = photoVideos[photoId] || [];
    return videos.find((v) => v.is_selected) || videos[0];
  };

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

  const isProcessing = project.status === "processing";
  const styledCount = photos.filter((p) => p.status === "styled").length;
  const stylingCount = photos.filter((p) => p.status === "styling").length;
  const canGenerate = project.style && photos.length > 0 && !isProcessing && !isApplyingStyle;

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex justify-between items-center">
          <div className="flex items-center gap-4">
            <Link to="/" className="text-gray-600 hover:text-gray-900">
              ← Back
            </Link>
            <h1 className="text-xl font-bold text-gray-900">{project.name}</h1>
            <span
              className={`px-2 py-1 text-xs rounded-full ${
                project.status === "complete"
                  ? "bg-green-100 text-green-700"
                  : project.status === "processing"
                  ? "bg-yellow-100 text-yellow-700"
                  : "bg-gray-100 text-gray-700"
              }`}
            >
              {project.status}
            </span>
            {project.style && (
              <span className="px-2 py-1 text-xs rounded-full bg-purple-100 text-purple-700">
                {project.style}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            {/* View Mode Toggle */}
            <div className="flex rounded-lg border border-gray-300 overflow-hidden">
              <button
                onClick={() => setViewMode("grid")}
                className={`px-3 py-1.5 text-sm ${
                  viewMode === "grid"
                    ? "bg-primary-600 text-white"
                    : "bg-white text-gray-700 hover:bg-gray-50"
                }`}
              >
                Grid
              </button>
              <button
                onClick={() => setViewMode("compare")}
                className={`px-3 py-1.5 text-sm ${
                  viewMode === "compare"
                    ? "bg-primary-600 text-white"
                    : "bg-white text-gray-700 hover:bg-gray-50"
                }`}
              >
                Compare
              </button>
            </div>
            <Link
              to={`/projects/${projectId}/export`}
              className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
            >
              Export Video
            </Link>
            <button
              onClick={() => setShowDeleteConfirm(true)}
              className="px-4 py-2 text-red-600 hover:text-red-700 hover:bg-red-50 rounded-lg transition-colors"
              title="Delete Project"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          </div>
        </div>
      </header>

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl p-6 max-w-md mx-4">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">
              Delete Project?
            </h3>
            <p className="text-gray-600 mb-4">
              Are you sure you want to delete "{project.name}"? This will permanently delete all photos, styled images, and videos. This action cannot be undone.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleDeleteProject}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
              >
                Delete Project
              </button>
            </div>
          </div>
        </div>
      )}

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {viewMode === "grid" ? (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            {/* Main Content */}
            <div className="lg:col-span-2 space-y-8">
              {/* Upload Section */}
              <section>
                <h2 className="text-lg font-semibold text-gray-900 mb-4">
                  Upload Photos
                </h2>
                <ImageUploader
                  projectId={projectId!}
                  onUploadComplete={handleUploadComplete}
                  onPhotosImported={loadProject}
                />
              </section>

              {/* Photos Grid */}
              <section>
                <div className="flex justify-between items-center mb-4">
                  <h2 className="text-lg font-semibold text-gray-900">
                    Photos ({photos.length})
                  </h2>
                  {selectedPhoto && (
                    <button
                      onClick={() => handleDeletePhoto(selectedPhoto.id)}
                      className="text-red-600 hover:text-red-700 text-sm"
                    >
                      Delete Selected
                    </button>
                  )}
                </div>
                <PhotoGallery
                  photos={photos}
                  onReorder={handleReorder}
                  onSelect={setSelectedPhoto}
                  selectedPhotoId={selectedPhoto?.id}
                  apiUrl={API_URL}
                />
              </section>
            </div>

            {/* Sidebar */}
            <div className="space-y-8">
              {/* Style Selection */}
              <section className="bg-white rounded-xl shadow-sm p-6">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">
                  Project Style
                </h2>

                {isProcessing && (
                  <div className="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-yellow-600"></div>
                        <span className="text-yellow-700 text-sm">
                          Generating styled images... ({styledCount}/{photos.length})
                        </span>
                      </div>
                      <button
                        onClick={handleResetStuck}
                        className="text-xs text-yellow-700 hover:text-yellow-900 underline"
                        title="Reset stuck photos if generation seems frozen"
                      >
                        Reset
                      </button>
                    </div>
                    {stylingCount > 0 && (
                      <p className="text-yellow-600 text-xs mt-1">
                        Currently processing {stylingCount} photo(s)
                      </p>
                    )}
                  </div>
                )}

                <div className="grid grid-cols-2 gap-3 mb-4">
                  {STYLES.map((style) => (
                    <button
                      key={style.id}
                      onClick={() => handleStyleSelect(style.id)}
                      disabled={isProcessing}
                      className={`p-3 rounded-lg text-center border-2 transition-colors ${
                        project.style === style.id
                          ? "border-primary-500 bg-primary-50"
                          : "border-gray-200 hover:border-gray-300"
                      } ${
                        isProcessing
                          ? "opacity-50 cursor-not-allowed"
                          : "cursor-pointer"
                      }`}
                    >
                      <div className="aspect-video bg-gray-100 rounded mb-2 flex items-center justify-center text-2xl">
                        {style.icon}
                      </div>
                      <span className="font-medium capitalize text-sm">
                        {style.label}
                      </span>
                    </button>
                  ))}
                </div>

                {/* Custom Style Prompt */}
                <div className="mb-4">
                  <button
                    onClick={() => setShowStylePrompt(!showStylePrompt)}
                    className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900"
                  >
                    <svg
                      className={`w-4 h-4 transition-transform ${showStylePrompt ? "rotate-90" : ""}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                    Customize Style Prompt
                    {stylePrompt && (
                      <span className="px-1.5 py-0.5 text-xs bg-purple-100 text-purple-700 rounded">
                        Custom
                      </span>
                    )}
                  </button>
                  {showStylePrompt && (
                    <div className="mt-2">
                      <textarea
                        value={stylePrompt}
                        onChange={(e) => setStylePrompt(e.target.value)}
                        placeholder="Enter a custom prompt for style transfer, or leave empty to use the default prompt for the selected style..."
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                        rows={4}
                      />
                      <p className="text-xs text-gray-400 mt-1">
                        Auto-saves as you type. Leave empty to use default style prompt.
                      </p>
                    </div>
                  )}
                </div>

                {/* Generate Button */}
                <button
                  onClick={handleGenerateStyledImages}
                  disabled={!canGenerate}
                  className={`w-full py-3 px-4 rounded-lg font-medium text-white transition-colors ${
                    canGenerate
                      ? "bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700"
                      : "bg-gray-400 cursor-not-allowed"
                  }`}
                >
                  {isProcessing || isApplyingStyle ? (
                    <span className="flex items-center justify-center gap-2">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                      <GeneratingTimer label="Generating" />
                    </span>
                  ) : (
                    `Generate ${project.style ? project.style.charAt(0).toUpperCase() + project.style.slice(1) : ""} Style`
                  )}
                </button>

                {photos.length === 0 && (
                  <p className="text-sm text-gray-500 mt-3 text-center">
                    Upload photos first
                  </p>
                )}
                {photos.length > 0 && !project.style && (
                  <p className="text-sm text-gray-500 mt-3 text-center">
                    Select a style above
                  </p>
                )}
              </section>

              {/* Selected Photo Details */}
              {selectedPhoto && (
                <section className="bg-white rounded-xl shadow-sm p-6">
                  <h2 className="text-lg font-semibold text-gray-900 mb-4">
                    Photo Details
                  </h2>
                  <div className="space-y-4">
                    <div
                      className="aspect-video bg-gray-100 rounded-lg overflow-hidden cursor-pointer hover:ring-2 hover:ring-primary-500 transition-all"
                      onClick={() =>
                        setLightboxImage({
                          url: `${API_URL}${selectedPhoto.styled_url || selectedPhoto.original_url}`,
                          alt: "Selected photo",
                        })
                      }
                    >
                      <img
                        src={`${API_URL}${
                          selectedPhoto.styled_url || selectedPhoto.original_url
                        }`}
                        alt="Selected"
                        className="w-full h-full object-cover"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Animation Prompt
                      </label>
                      <textarea
                        value={animationPrompt}
                        onChange={(e) => setAnimationPrompt(e.target.value)}
                        placeholder="Describe how this photo should animate..."
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                        rows={3}
                      />
                      <p className="text-xs text-gray-400 mt-1">Auto-saves as you type</p>
                    </div>
                    <div className="flex items-center justify-between">
                      <span
                        className={`px-2 py-1 text-xs rounded-full ${
                          selectedPhoto.status === "ready"
                            ? "bg-green-100 text-green-700"
                            : selectedPhoto.status === "styled"
                            ? "bg-blue-100 text-blue-700"
                            : selectedPhoto.status === "styling"
                            ? "bg-yellow-100 text-yellow-700"
                            : "bg-gray-100 text-gray-700"
                        }`}
                      >
                        {selectedPhoto.status}
                      </span>
                      {selectedPhoto.styled_url && project.style && (
                        <button
                          onClick={() => handleRegeneratePhoto(selectedPhoto.id)}
                          disabled={selectedPhoto.status === "styling"}
                          className="text-sm text-primary-600 hover:text-primary-700 disabled:opacity-50"
                        >
                          Regenerate Style
                        </button>
                      )}
                    </div>

                    {/* Video Generation Section */}
                    {selectedPhoto.styled_url && (
                      <div className="pt-4 border-t border-gray-200">
                        <div className="flex items-center justify-between mb-3">
                          <h3 className="text-sm font-medium text-gray-900">Animation Video</h3>
                          {getSelectedVideo(selectedPhoto.id) && (
                            <span
                              className={`px-2 py-1 text-xs rounded-full ${
                                getSelectedVideo(selectedPhoto.id)?.status === "ready"
                                  ? "bg-green-100 text-green-700"
                                  : getSelectedVideo(selectedPhoto.id)?.status === "generating"
                                  ? "bg-yellow-100 text-yellow-700"
                                  : getSelectedVideo(selectedPhoto.id)?.status === "failed"
                                  ? "bg-red-100 text-red-700"
                                  : "bg-gray-100 text-gray-700"
                              }`}
                            >
                              {getSelectedVideo(selectedPhoto.id)?.status}
                            </span>
                          )}
                        </div>

                        {/* Video Preview - Selected Video */}
                        {getSelectedVideo(selectedPhoto.id)?.video_url &&
                         getSelectedVideo(selectedPhoto.id)?.status === "ready" && (
                          <div className="aspect-video bg-black rounded-lg overflow-hidden mb-3">
                            <video
                              src={`${API_URL}${getSelectedVideo(selectedPhoto.id)?.video_url}`}
                              controls
                              className="w-full h-full object-contain"
                            />
                          </div>
                        )}

                        {/* Generating State */}
                        {(generatingVideos[selectedPhoto.id] ||
                          getSelectedVideo(selectedPhoto.id)?.status === "generating") && (
                          <div className="aspect-video bg-gray-100 rounded-lg flex items-center justify-center mb-3">
                            <div className="text-center">
                              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600 mx-auto mb-2"></div>
                              <p className="text-xs text-gray-500">
                                <GeneratingTimer label="Generating video" />
                              </p>
                            </div>
                          </div>
                        )}

                        {/* Video Variants Gallery */}
                        {(photoVideos[selectedPhoto.id]?.length || 0) > 1 && (
                          <div className="mb-3">
                            <p className="text-xs text-gray-600 mb-2">
                              All Videos ({photoVideos[selectedPhoto.id]?.length}) - Click to select:
                            </p>
                            <div className="flex gap-2 overflow-x-auto pb-2">
                              {photoVideos[selectedPhoto.id]?.filter(v => v.status === "ready").map((video) => (
                                <button
                                  key={video.id}
                                  onClick={() => handleSelectVideo(selectedPhoto.id, video.id)}
                                  className={`flex-shrink-0 relative rounded-lg overflow-hidden border-2 transition-all ${
                                    video.is_selected
                                      ? "border-primary-500 ring-2 ring-primary-200"
                                      : "border-gray-200 hover:border-gray-300"
                                  }`}
                                >
                                  <video
                                    src={`${API_URL}${video.video_url}`}
                                    className="w-20 h-20 object-cover"
                                    muted
                                  />
                                  {video.is_selected && (
                                    <div className="absolute top-1 right-1 bg-primary-500 text-white rounded-full p-0.5">
                                      <svg
                                        className="w-3 h-3"
                                        fill="currentColor"
                                        viewBox="0 0 20 20"
                                      >
                                        <path
                                          fillRule="evenodd"
                                          d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                                          clipRule="evenodd"
                                        />
                                      </svg>
                                    </div>
                                  )}
                                </button>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Generate Button */}
                        <button
                          onClick={() => handleGenerateVideo(selectedPhoto.id)}
                          disabled={
                            !animationPrompt ||
                            generatingVideos[selectedPhoto.id] ||
                            getSelectedVideo(selectedPhoto.id)?.status === "generating"
                          }
                          className={`w-full py-2 px-4 rounded-lg font-medium text-sm transition-colors ${
                            !animationPrompt ||
                            generatingVideos[selectedPhoto.id] ||
                            getSelectedVideo(selectedPhoto.id)?.status === "generating"
                              ? "bg-gray-300 text-gray-500 cursor-not-allowed"
                              : "bg-gradient-to-r from-indigo-600 to-purple-600 text-white hover:from-indigo-700 hover:to-purple-700"
                          }`}
                        >
                          {generatingVideos[selectedPhoto.id] ||
                           getSelectedVideo(selectedPhoto.id)?.status === "generating" ? (
                            <span className="flex items-center justify-center gap-2">
                              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                              <GeneratingTimer label="Generating" />
                            </span>
                          ) : getSelectedVideo(selectedPhoto.id)?.video_url ? (
                            "Regenerate Video"
                          ) : (
                            "Generate Video"
                          )}
                        </button>

                        {!animationPrompt && (
                          <p className="text-xs text-gray-400 mt-2 text-center">
                            Add an animation prompt above first
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                </section>
              )}
            </div>
          </div>
        ) : (
          /* Compare View */
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-900">
                Original vs Styled Comparison
              </h2>
              {project.style && (
                <span className="px-3 py-1 text-sm rounded-full bg-purple-100 text-purple-700">
                  {project.style.charAt(0).toUpperCase() + project.style.slice(1)} Style
                </span>
              )}
            </div>

            {photos.length === 0 ? (
              <div className="text-center py-12 bg-white rounded-xl shadow-sm">
                <p className="text-gray-500">No photos uploaded yet</p>
              </div>
            ) : (
              <div className="space-y-6">
                {photos.map((photo, index) => {
                  const variants = photoVariants[photo.id] || [];
                  const isRegenerating = loadingVariants[photo.id];
                  const videos = photoVideos[photo.id] || [];
                  const video = getSelectedVideo(photo.id);
                  const isGeneratingVideo = generatingVideos[photo.id];

                  return (
                    <div
                      key={photo.id}
                      className="bg-white rounded-xl shadow-sm p-6"
                    >
                      <div className="flex items-center justify-between mb-4">
                        <h3 className="font-medium text-gray-900">
                          Photo {index + 1}
                        </h3>
                        <div className="flex items-center gap-3">
                          <span
                            className={`px-2 py-1 text-xs rounded-full ${
                              photo.status === "styled"
                                ? "bg-blue-100 text-blue-700"
                                : photo.status === "styling"
                                ? "bg-yellow-100 text-yellow-700"
                                : "bg-gray-100 text-gray-700"
                            }`}
                          >
                            {photo.status}
                          </span>
                          {photo.styled_url && project.style && (
                            <button
                              onClick={() => handleRegeneratePhoto(photo.id)}
                              disabled={photo.status === "styling" || isRegenerating}
                              className="text-sm text-primary-600 hover:text-primary-700 disabled:opacity-50"
                            >
                              {photo.status === "styling" || isRegenerating ? (
                                <span className="flex items-center gap-1">
                                  <div className="animate-spin rounded-full h-3 w-3 border-b border-primary-600"></div>
                                  <GeneratingTimer label="Generating" />
                                </span>
                              ) : (
                                "Regenerate"
                              )}
                            </button>
                          )}
                        </div>
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {/* Original */}
                        <div>
                          <p className="text-sm text-gray-500 mb-2 text-center">
                            Original
                          </p>
                          <div
                            className="aspect-video bg-gray-100 rounded-lg overflow-hidden cursor-pointer hover:ring-2 hover:ring-primary-500 transition-all"
                            onClick={() =>
                              setLightboxImage({
                                url: `${API_URL}${photo.original_url}`,
                                alt: `Original ${index + 1}`,
                              })
                            }
                          >
                            <img
                              src={`${API_URL}${photo.original_url}`}
                              alt={`Original ${index + 1}`}
                              className="w-full h-full object-cover"
                            />
                          </div>
                        </div>

                        {/* Styled */}
                        <div>
                          <p className="text-sm text-gray-500 mb-2 text-center">
                            Styled (Selected)
                          </p>
                          <div className="aspect-video bg-gray-100 rounded-lg overflow-hidden">
                            {photo.styled_url ? (
                              <img
                                src={`${API_URL}${photo.styled_url}`}
                                alt={`Styled ${index + 1}`}
                                className="w-full h-full object-cover cursor-pointer hover:ring-2 hover:ring-primary-500 transition-all"
                                onClick={() =>
                                  setLightboxImage({
                                    url: `${API_URL}${photo.styled_url}`,
                                    alt: `Styled ${index + 1}`,
                                  })
                                }
                              />
                            ) : photo.status === "styling" ? (
                              <div className="w-full h-full flex items-center justify-center">
                                <div className="text-center">
                                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600 mx-auto mb-2"></div>
                                  <p className="text-sm text-gray-500">
                                    <GeneratingTimer label="Generating" />
                                  </p>
                                </div>
                              </div>
                            ) : (
                              <div className="w-full h-full flex items-center justify-center">
                                <p className="text-sm text-gray-400">
                                  Not yet generated
                                </p>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Variants Gallery */}
                      {variants.length > 1 && (
                        <div className="mt-4">
                          <p className="text-sm text-gray-600 mb-2">
                            All Variants ({variants.length}) - Click to select:
                          </p>
                          <div className="flex gap-2 overflow-x-auto pb-2">
                            {variants.map((variant) => (
                              <button
                                key={variant.id}
                                onClick={() => handleSelectVariant(photo.id, variant.id)}
                                className={`flex-shrink-0 relative rounded-lg overflow-hidden border-2 transition-all ${
                                  variant.is_selected
                                    ? "border-primary-500 ring-2 ring-primary-200"
                                    : "border-gray-200 hover:border-gray-300"
                                }`}
                              >
                                <img
                                  src={`${API_URL}${variant.styled_url}`}
                                  alt="Variant"
                                  className="w-24 h-24 object-cover"
                                />
                                {variant.is_selected && (
                                  <div className="absolute top-1 right-1 bg-primary-500 text-white rounded-full p-0.5">
                                    <svg
                                      className="w-3 h-3"
                                      fill="currentColor"
                                      viewBox="0 0 20 20"
                                    >
                                      <path
                                        fillRule="evenodd"
                                        d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                                        clipRule="evenodd"
                                      />
                                    </svg>
                                  </div>
                                )}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Video Generation Section */}
                      {photo.styled_url && (
                        <div className="mt-6 pt-4 border-t border-gray-200">
                          <div className="flex items-center justify-between mb-3">
                            <h4 className="font-medium text-gray-900">Animation Video</h4>
                            {video && (
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
                            )}
                          </div>

                          {/* Video Preview */}
                          {video?.video_url && video.status === "ready" ? (
                            <div className="aspect-video bg-black rounded-lg overflow-hidden mb-3">
                              <video
                                src={`${API_URL}${video.video_url}`}
                                controls
                                className="w-full h-full object-contain"
                              />
                            </div>
                          ) : isGeneratingVideo || video?.status === "generating" ? (
                            <div className="aspect-video bg-gray-100 rounded-lg flex items-center justify-center mb-3">
                              <div className="text-center">
                                <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary-600 mx-auto mb-3"></div>
                                <p className="text-sm text-gray-600">
                                  <GeneratingTimer label="Generating video" />
                                </p>
                                <p className="text-xs text-gray-400 mt-1">
                                  Using Kling AI
                                </p>
                              </div>
                            </div>
                          ) : video?.status === "failed" ? (
                            <div className="aspect-video bg-red-50 rounded-lg flex items-center justify-center mb-3">
                              <div className="text-center">
                                <p className="text-sm text-red-600 mb-2">
                                  Video generation failed
                                </p>
                                <button
                                  onClick={() => handleGenerateVideo(photo.id)}
                                  className="text-sm text-primary-600 hover:text-primary-700"
                                >
                                  Try Again
                                </button>
                              </div>
                            </div>
                          ) : null}

                          {/* Animation Prompt */}
                          <div className="mb-3">
                            <p className="text-xs text-gray-500 mb-1">Animation Prompt:</p>
                            <p className="text-sm text-gray-700 bg-gray-50 rounded p-2">
                              {photo.animation_prompt || (
                                <span className="text-gray-400 italic">
                                  No animation prompt set. Add one in Grid view.
                                </span>
                              )}
                            </p>
                          </div>

                          {/* Video Variants Gallery */}
                          {videos.filter(v => v.status === "ready").length > 1 && (
                            <div className="mb-3">
                              <p className="text-xs text-gray-600 mb-2">
                                All Videos ({videos.filter(v => v.status === "ready").length}) - Click to select:
                              </p>
                              <div className="flex gap-2 overflow-x-auto pb-2">
                                {videos.filter(v => v.status === "ready").map((v) => (
                                  <button
                                    key={v.id}
                                    onClick={() => handleSelectVideo(photo.id, v.id)}
                                    className={`flex-shrink-0 relative rounded-lg overflow-hidden border-2 transition-all ${
                                      v.is_selected
                                        ? "border-primary-500 ring-2 ring-primary-200"
                                        : "border-gray-200 hover:border-gray-300"
                                    }`}
                                  >
                                    <video
                                      src={`${API_URL}${v.video_url}`}
                                      className="w-20 h-20 object-cover"
                                      muted
                                    />
                                    {v.is_selected && (
                                      <div className="absolute top-1 right-1 bg-primary-500 text-white rounded-full p-0.5">
                                        <svg
                                          className="w-3 h-3"
                                          fill="currentColor"
                                          viewBox="0 0 20 20"
                                        >
                                          <path
                                            fillRule="evenodd"
                                            d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                                            clipRule="evenodd"
                                          />
                                        </svg>
                                      </div>
                                    )}
                                  </button>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Generate Button */}
                          <button
                            onClick={() => handleGenerateVideo(photo.id)}
                            disabled={
                              !photo.animation_prompt ||
                              isGeneratingVideo ||
                              video?.status === "generating"
                            }
                            className={`w-full py-2 px-4 rounded-lg font-medium text-sm transition-colors ${
                              !photo.animation_prompt ||
                              isGeneratingVideo ||
                              video?.status === "generating"
                                ? "bg-gray-300 text-gray-500 cursor-not-allowed"
                                : "bg-gradient-to-r from-indigo-600 to-purple-600 text-white hover:from-indigo-700 hover:to-purple-700"
                            }`}
                          >
                            {isGeneratingVideo || video?.status === "generating" ? (
                              <span className="flex items-center justify-center gap-2">
                                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                                <GeneratingTimer label="Generating" />
                              </span>
                            ) : video?.video_url ? (
                              "Regenerate Video"
                            ) : (
                              "Generate Video"
                            )}
                          </button>

                          {!photo.animation_prompt && (
                            <p className="text-xs text-gray-400 mt-2 text-center">
                              Add an animation prompt in Grid view to generate a video
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </main>

      {/* Lightbox */}
      {lightboxImage && (
        <Lightbox
          imageUrl={lightboxImage.url}
          alt={lightboxImage.alt}
          onClose={() => setLightboxImage(null)}
        />
      )}
    </div>
  );
}
