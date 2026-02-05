import { useState } from "react";
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
import type { Photo } from "../../types";

interface PhotoGalleryProps {
  photos: Photo[];
  onReorder: (photos: Photo[]) => void;
  onSelect: (photo: Photo) => void;
  selectedPhotoId?: string;
  apiUrl: string;
}

interface SortablePhotoProps {
  photo: Photo;
  isSelected: boolean;
  onClick: () => void;
  apiUrl: string;
  showOriginal: boolean;
}

function SortablePhoto({
  photo,
  isSelected,
  onClick,
  apiUrl,
  showOriginal,
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
        {photo.style && (
          <span className="ml-1 px-2 py-0.5 text-xs rounded-full bg-purple-500 text-white">
            {photo.style}
          </span>
        )}
      </div>
    </div>
  );
}

export default function PhotoGallery({
  photos,
  onReorder,
  onSelect,
  selectedPhotoId,
  apiUrl,
}: PhotoGalleryProps) {
  const [showOriginal, setShowOriginal] = useState(false);
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    })
  );

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
    <div>
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
                apiUrl={apiUrl}
                showOriginal={showOriginal}
              />
            ))}
          </div>
        </SortableContext>
      </DndContext>
    </div>
  );
}
