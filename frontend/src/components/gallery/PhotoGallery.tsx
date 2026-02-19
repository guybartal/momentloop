import React, { useState, useRef, useEffect } from "react";
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
  onDelete?: (photoId: string) => void;
  onRestyle?: (photoId: string, style: StyleType, customPrompt?: string) => void;
  selectedPhotoId?: string;
  apiUrl: string;
  currentStyle?: StyleType | null;
}

interface SortablePhotoProps {
  photo: Photo;
  isSelected: boolean;
  onClick: () => void;
  onDeleteClick: (e: React.MouseEvent) => void;
  onRestyleClick: (e: React.MouseEvent) => void;
  apiUrl: string;
  showOriginal: boolean;
  onToggleOriginal: (e: React.MouseEvent) => void;
  showRestyleButton: boolean;
}

function SortablePhoto({
  photo,
  isSelected,
  onClick,
  onDeleteClick,
  onRestyleClick,
  apiUrl,
  showOriginal,
  onToggleOriginal,
  showRestyleButton,
}: SortablePhotoProps) {
  const [confirmDelete, setConfirmDelete] = useState(false);
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
      className={`group relative bg-white dark:bg-gray-800 rounded-lg shadow-sm overflow-hidden cursor-pointer transition-all ${
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
      {/* Top right buttons */}
      <div className="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        {/* Show original toggle */}
        {photo.styled_url && (
          <button
            onClick={onToggleOriginal}
            className={`p-1.5 rounded-full shadow transition-colors ${
              showOriginal
                ? "bg-gray-700/90 text-white"
                : "bg-white/90 dark:bg-gray-800/90 text-gray-600 dark:text-gray-400 hover:bg-white dark:hover:bg-gray-700"
            }`}
            title={showOriginal ? "Show styled" : "Show original"}
            aria-label={showOriginal ? "Show styled image" : "Show original image"}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              {showOriginal ? (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.878 9.878L3 3m6.878 6.878L21 21" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              )}
            </svg>
          </button>
        )}
        {/* Restyle button */}
        {showRestyleButton && photo.status !== "styling" && (
          <button
            onClick={onRestyleClick}
            className="p-1.5 bg-white/90 dark:bg-gray-800/90 rounded-full shadow hover:bg-white dark:hover:bg-gray-700 transition-colors"
            title="Restyle this photo"
          >
            <svg className="w-4 h-4 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        )}
        {/* Delete button with confirm popup */}
        <div className="relative">
          <button
            onClick={(e: React.MouseEvent) => {
              e.stopPropagation();
              setConfirmDelete(!confirmDelete);
            }}
            className="p-1.5 bg-white/90 dark:bg-gray-800/90 rounded-full shadow hover:bg-red-50 dark:hover:bg-red-900/40 transition-colors"
            title="Delete photo"
            aria-label="Delete photo"
          >
            <svg className="w-4 h-4 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
          </button>
          {confirmDelete && (
            <div className="absolute right-0 top-full mt-1 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-600 p-2 z-10 whitespace-nowrap">
              <p className="text-xs text-gray-600 dark:text-gray-400 mb-2">Delete this photo?</p>
              <div className="flex gap-1">
                <button
                  onClick={(e: React.MouseEvent) => {
                    e.stopPropagation();
                    setConfirmDelete(false);
                    onDeleteClick(e);
                  }}
                  className="px-2 py-1 text-xs bg-red-600 text-white rounded hover:bg-red-700 transition-colors"
                >
                  Delete
                </button>
                <button
                  onClick={(e: React.MouseEvent) => {
                    e.stopPropagation();
                    setConfirmDelete(false);
                  }}
                  className="px-2 py-1 text-xs text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
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
  onDelete,
  onRestyle,
  selectedPhotoId,
  apiUrl,
  currentStyle,
}: PhotoGalleryProps) {
  const [showOriginalIds, setShowOriginalIds] = useState<Set<string>>(new Set());
  const [restylePhotoId, setRestylePhotoId] = useState<string | null>(null);
  const [restyleStyle, setRestyleStyle] = useState<StyleType>(currentStyle || "ghibli");
  const [restylePrompt, setRestylePrompt] = useState("");
  const popupRef = useRef<HTMLDivElement>(null);
  // Track styled URLs to detect when any photo gets a new/updated styled image
  const prevStyledUrlsRef = useRef<string>("");

  // Auto-switch to styled view when a photo gets newly styled while viewing original
  useEffect(() => {
    const currentStyledUrls = photos
      .map((p) => `${p.id}:${p.styled_url || ""}`)
      .join(",");
    const prev = prevStyledUrlsRef.current;

    if (prev && showOriginalIds.size > 0 && currentStyledUrls !== prev) {
      // Check which photos gained or changed a styled_url
      const prevMap = new Map(
        prev.split(",").map((entry: string) => {
          const [id, ...rest] = entry.split(":");
          return [id, rest.join(":")] as [string, string];
        })
      );
      const newlyStyledIds = photos
        .filter((p) => {
          const prevUrl = prevMap.get(p.id) || "";
          return p.styled_url && p.styled_url !== prevUrl;
        })
        .map((p) => p.id);
      if (newlyStyledIds.length > 0) {
        setShowOriginalIds((prev: Set<string>) => {
          const next = new Set(prev);
          newlyStyledIds.forEach((id) => next.delete(id));
          return next;
        });
      }
    }
    prevStyledUrlsRef.current = currentStyledUrls;
  }, [photos, showOriginalIds]);

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

  if (photos.length === 0) {
    return (
      <p className="text-gray-500 dark:text-gray-400 text-center py-8">
        No photos yet. Upload some to get started.
      </p>
    );
  }

  return (
    <div className="relative">
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
                onDeleteClick={(e) => {
                  e.stopPropagation();
                  onDelete?.(photo.id);
                }}
                onRestyleClick={(e) => handleRestyleClick(e, photo.id)}
                apiUrl={apiUrl}
                showOriginal={showOriginalIds.has(photo.id)}
                onToggleOriginal={(e) => {
                  e.stopPropagation();
                  setShowOriginalIds((prev: Set<string>) => {
                    const next = new Set(prev);
                    if (next.has(photo.id)) {
                      next.delete(photo.id);
                    } else {
                      next.add(photo.id);
                    }
                    return next;
                  });
                }}
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
