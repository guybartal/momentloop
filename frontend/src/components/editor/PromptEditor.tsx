import { useState } from "react";
import api from "../../services/api";

interface PromptEditorProps {
  photoId: string;
  initialPrompt: string | null;
  onPromptChange: (prompt: string) => void;
}

export default function PromptEditor({
  photoId,
  initialPrompt,
  onPromptChange,
}: PromptEditorProps) {
  const [prompt, setPrompt] = useState(initialPrompt || "");
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const generatePrompt = async () => {
    setIsGenerating(true);
    try {
      const response = await api.post<{ animation_prompt: string }>(
        `/photos/${photoId}/generate-prompt`
      );
      setPrompt(response.data.animation_prompt);
      onPromptChange(response.data.animation_prompt);
    } catch (error) {
      console.error("Failed to generate prompt:", error);
    } finally {
      setIsGenerating(false);
    }
  };

  const savePrompt = async () => {
    setIsSaving(true);
    try {
      await api.put(`/photos/${photoId}`, { animation_prompt: prompt });
      onPromptChange(prompt);
    } catch (error) {
      console.error("Failed to save prompt:", error);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <label className="block text-sm font-medium text-gray-700">
          Animation Prompt
        </label>
        <button
          onClick={generatePrompt}
          disabled={isGenerating}
          className="text-xs text-primary-600 hover:text-primary-700 disabled:opacity-50"
        >
          {isGenerating ? "Generating..." : "Generate with AI"}
        </button>
      </div>
      <textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="Describe how this photo should animate..."
        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 resize-none"
        rows={4}
      />
      <div className="flex justify-end">
        <button
          onClick={savePrompt}
          disabled={isSaving || prompt === initialPrompt}
          className="px-4 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isSaving ? "Saving..." : "Save Prompt"}
        </button>
      </div>
    </div>
  );
}
