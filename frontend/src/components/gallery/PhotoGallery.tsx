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
}

function SortablePhoto({
  photo,
  isSelected,
  onClick,
  apiUrl,
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

  const imageUrl = photo.styled_url
    ? `${apiUrl}${photo.styled_url}`
    : `${apiUrl}${photo.original_url}`;

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onClick={onClick}
      className={`relative bg-white rounded-lg shadow-sm overflow-hidden cursor-pointer transition-all ${
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
      <div className="absolute top-2 left-2 bg-black/50 text-white px-2 py-0.5 rounded text-sm">
        {photo.position + 1}
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

  if (photos.length === 0) {
    return (
      <p className="text-gray-500 text-center py-8">
        No photos yet. Upload some to get started.
      </p>
    );
  }

  return (
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
            />
          ))}
        </div>
      </SortableContext>
    </DndContext>
  );
}
