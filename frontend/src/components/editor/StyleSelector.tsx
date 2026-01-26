import type { StyleType } from "../../types";

interface StyleSelectorProps {
  selectedStyle: StyleType | null;
  onSelect: (style: StyleType) => void;
  disabled?: boolean;
}

const STYLES: { id: StyleType; name: string; emoji: string; description: string }[] = [
  {
    id: "ghibli",
    name: "Studio Ghibli",
    emoji: "🏯",
    description: "Dreamy anime style with soft colors",
  },
  {
    id: "lego",
    name: "LEGO",
    emoji: "🧱",
    description: "Blocky brick-built characters",
  },
  {
    id: "minecraft",
    name: "Minecraft",
    emoji: "⛏️",
    description: "Pixelated cubic world",
  },
  {
    id: "simpsons",
    name: "Simpsons",
    emoji: "💛",
    description: "Yellow cartoon characters",
  },
];

export default function StyleSelector({
  selectedStyle,
  onSelect,
  disabled = false,
}: StyleSelectorProps) {
  return (
    <div className="grid grid-cols-2 gap-3">
      {STYLES.map((style) => (
        <button
          key={style.id}
          onClick={() => onSelect(style.id)}
          disabled={disabled}
          className={`p-4 rounded-xl text-left border-2 transition-all ${
            selectedStyle === style.id
              ? "border-primary-500 bg-primary-50 shadow-md"
              : "border-gray-200 hover:border-gray-300 bg-white"
          } ${disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
        >
          <div className="text-3xl mb-2">{style.emoji}</div>
          <div className="font-medium text-gray-900">{style.name}</div>
          <div className="text-xs text-gray-500 mt-1">{style.description}</div>
        </button>
      ))}
    </div>
  );
}
