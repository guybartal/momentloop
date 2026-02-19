import { useState, useRef, useEffect } from "react";
import {
  DndContext,
  DragEndEvent,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  rectSortingStrategy,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { Photo, StyleType } from "../../types";

const STYLES: { id: StyleType; label: string; icon: string }[] = [
  { id: "ghibli", label: "Ghibli", icon: "🏯" },
  { id: "lego", label: "Lego", icon: "🧱" },
  { id: "minecraft", label: "Minecraft", icon: "⛏️" },
  { id: "simpsons", label: "Simpsons", icon: "💛" },
];

const DEFAULT_STYLE_PROMPTS: Record<StyleType, string> = {
  ghibli: "Restyle this image with Studio Ghibli style.",
  lego: "Restyle this image with LEGO style.",
  minecraft: "Restyle this image with Minecraft style.",
  simpsons: "Restyle this image with The Simpsons style.",
};

interface PhotoGalleryProps {
  photos: Photo[];
  onReorder: (photos: Photo[]) => void;
  onSelect: (photo: Photo) => void;
  onRestyle?: (photoId: string, style: StyleType, customPrompt?: string) => void;
  selectedPhotoId?: string;
  apiUrl: string;
  currentStyle?: StyleType | null;
}

interface SortablePhotoProps {
  photo: Photo;
  isSelected: boolean;
  onClick: () => void;
  onRestyleClick: (e: React.MouseEvent) => void;
  apiUrl: string;
  showOriginal: boolean;
  showRestyleButton: boolean;
}

function SortablePhoto({
  photo,
  isSelected,
  onClick,
  onRestyleClick,
  apiUrl,
  showOriginal,
  showRestyleButton,
}: SortablePhotoProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: photo.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  const imageUrl = showOriginal || !photo.styled_url
    ? `${apiUrl}${photo.original_url}`
    : `${apiUrl}${photo.styled_url}`;

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onClick={onClick}
      className={`relative bg-white dark:bg-gray-800 rounded-lg shadow-sm overflow-hidden cursor-pointer transition-all ${
        isDragging ? "opacity-50 scale-105" : ""
      } ${isSelected ? "ring-2 ring-primary-500" : "hover:shadow-md"}`}
    >
      <div className="aspect-square">
        <img
          src={imageUrl}
          alt={`Photo ${photo.position + 1}`}
          className="w-full h-full object-cover"
          draggable={false}
        />
      </div>
      {/* Restyle button - top right */}
      {showRestyleButton && photo.status !== "styling" && (
        <button
          onClick={onRestyleClick}
          className="absolute top-2 right-2 p-1.5 bg-white/90 dark:bg-gray-800/90 rounded-full shadow hover:bg-white dark:hover:bg-gray-700 transition-colors"
          title="Restyle this photo"
        >
          <svg className="w-4 h-4 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        </button>
      )}
      {/* Styling spinner */}
      {photo.status === "styling" && (
        <div className="absolute inset-0 bg-black/40 flex items-center justify-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
        </div>
      )}
      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/50 to-transparent p-2">
        <span
          className={`px-2 py-0.5 text-xs rounded-full ${
            photo.status === "ready"
              ? "bg-green-500 text-white"
              : photo.status === "styled"
              ? "bg-blue-500 text-white"
              : photo.status === "styling"
              ? "bg-yellow-500 text-white"
              : "bg-gray-500 text-white"
          }`}
        >
          {photo.status}
        </span>
      </div>
    </div>
  );
}

export default function PhotoGallery({
  photos,
  onReorder,
  onSelect,
  onRestyle,
  selectedPhotoId,
  apiUrl,
  currentStyle,
}: PhotoGalleryProps) {
  const [showOriginal, setShowOriginal] = useState(false);
  const [restylePhotoId, setRestylePhotoId] = useState<string | null>(null);
  const [restyleStyle, setRestyleStyle] = useState<StyleType>(currentStyle || "ghibli");
  const [restylePrompt, setRestylePrompt] = useState("");
  const popupRef = useRef<HTMLDivElement>(null);
  // Track styled URLs to detect when any photo gets a new/updated styled image
  const prevStyledUrlsRef = useRef<string>("");

  // Auto-switch to styled view when a photo gets newly styled while viewing originals
  useEffect(() => {
    const currentStyledUrls = photos
      .map((p) => `${p.id}:${p.styled_url || ""}`)
      .join(",");
    const prev = prevStyledUrlsRef.current;

    if (prev && showOriginal && currentStyledUrls !== prev) {
      // Check if any photo gained or changed a styled_url
      const prevMap = new Map(
        prev.split(",").map((entry: string) => {
          const [id, ...rest] = entry.split(":");
          return [id, rest.join(":")] as [string, string];
        })
      );
      const hasNewStyled = photos.some((p) => {
        const prevUrl = prevMap.get(p.id) || "";
        return p.styled_url && p.styled_url !== prevUrl;
      });
      if (hasNewStyled) {
        setShowOriginal(false);
      }
    }
    prevStyledUrlsRef.current = currentStyledUrls;
  }, [photos, showOriginal]);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    })
  );

  // Close popup when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (popupRef.current && !popupRef.current.contains(e.target as Node)) {
        setRestylePhotoId(null);
      }
    };
    if (restylePhotoId) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [restylePhotoId]);

  // Update default prompt when style changes
  useEffect(() => {
    setRestylePrompt(DEFAULT_STYLE_PROMPTS[restyleStyle]);
  }, [restyleStyle]);

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;

    if (over && active.id !== over.id) {
      const oldIndex = photos.findIndex((p) => p.id === active.id);
      const newIndex = photos.findIndex((p) => p.id === over.id);
      const reordered = arrayMove(photos, oldIndex, newIndex).map(
        (photo, index) => ({
          ...photo,
          position: index,
        })
      );
      onReorder(reordered);
    }
  };

  const handleRestyleClick = (e: React.MouseEvent, photoId: string) => {
    e.stopPropagation();
    setRestylePhotoId(photoId);
    setRestyleStyle(currentStyle || "ghibli");
    setRestylePrompt(DEFAULT_STYLE_PROMPTS[currentStyle || "ghibli"]);
  };

  const handleRestyleSubmit = () => {
    if (restylePhotoId && onRestyle) {
      onRestyle(restylePhotoId, restyleStyle, restylePrompt);
      setRestylePhotoId(null);
    }
  };

  // Check if any photos have styled versions
  const hasStyledPhotos = photos.some((p) => p.styled_url);

  if (photos.length === 0) {
    return (
      <p className="text-gray-500 dark:text-gray-400 text-center py-8">
        No photos yet. Upload some to get started.
      </p>
    );
  }

  return (
    <div className="relative">
      {/* Toggle button */}
      {hasStyledPhotos && (
        <div className="flex justify-end mb-3">
          <button
            onClick={() => setShowOriginal(!showOriginal)}
            className={`flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg border transition-colors ${
              showOriginal
                ? "bg-gray-100 dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300"
                : "bg-purple-50 dark:bg-purple-900/30 border-purple-300 dark:border-purple-700 text-purple-700 dark:text-purple-300"
            }`}
          >
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
            {showOriginal ? "Show Styled" : "Show Original"}
          </button>
        </div>
      )}

      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <SortableContext
          items={photos.map((p) => p.id)}
          strategy={rectSortingStrategy}
        >
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
            {photos.map((photo) => (
              <SortablePhoto
                key={photo.id}
                photo={photo}
                isSelected={photo.id === selectedPhotoId}
                onClick={() => onSelect(photo)}
                onRestyleClick={(e) => handleRestyleClick(e, photo.id)}
                apiUrl={apiUrl}
                showOriginal={showOriginal}
                showRestyleButton={!!onRestyle}
              />
            ))}
          </div>
        </SortableContext>
      </DndContext>

      {/* Restyle Popup */}
      {restylePhotoId && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div
            ref={popupRef}
            className="bg-white dark:bg-gray-800 rounded-xl shadow-xl p-6 w-full max-w-md mx-4"
          >
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
              Restyle Photo
            </h3>

            {/* Style Selection */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Style
              </label>
              <div className="grid grid-cols-4 gap-2">
                {STYLES.map((style) => (
                  <button
                    key={style.id}
                    onClick={() => setRestyleStyle(style.id)}
                    className={`p-2 rounded-lg text-center border-2 transition-colors ${
                      restyleStyle === style.id
                        ? "border-purple-500 bg-purple-50 dark:bg-purple-900/20"
                        : "border-gray-200 dark:border-gray-600 hover:border-gray-300"
                    }`}
                  >
                    <div className="text-xl mb-1">{style.icon}</div>
                    <span className="text-xs text-gray-700 dark:text-gray-300">{style.label}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Custom Prompt */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Prompt
              </label>
              <textarea
                value={restylePrompt}
                onChange={(e) => setRestylePrompt(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                rows={3}
                placeholder="Describe the style..."
              />
            </div>

            {/* Actions */}
            <div className="flex gap-3">
              <button
                onClick={() => setRestylePhotoId(null)}
                className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
              >
                Cancel
              </button>
              <button
                onClick={handleRestyleSubmit}
                className="flex-1 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700"
              >
                Restyle
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
