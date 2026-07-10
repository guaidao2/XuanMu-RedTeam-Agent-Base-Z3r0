import { X } from "lucide-react";
import { useEffect, useState, type WheelEvent } from "react";
import type { AgentImageInputPart } from "../../shared/api/types";

export type ImagePreviewState = { src: string; alt: string } | null;

export function imageDataUrl(image: AgentImageInputPart): string {
  return `data:${image.media_type};base64,${image.data}`;
}

export function ImagePreview({
  preview,
  onClose,
}: {
  preview: ImagePreviewState;
  onClose: () => void;
}) {
  const [scale, setScale] = useState(1);

  useEffect(() => {
    if (!preview) return;
    setScale(1);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose, preview]);

  if (!preview) return null;

  const handleWheel = (event: WheelEvent<HTMLDivElement>) => {
    event.preventDefault();
    const delta = event.deltaY > 0 ? -0.12 : 0.12;
    setScale((value) => Math.min(4, Math.max(0.3, Number((value + delta).toFixed(2)))));
  };

  return (
    <div
      className="image-preview-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="Image preview"
      onClick={onClose}
      onWheel={handleWheel}
    >
      <button
        type="button"
        className="image-preview-close"
        onClick={onClose}
        aria-label="Close image preview"
        title="Close"
      >
        <X size={20} />
      </button>
      <div className="image-preview-stage">
        <img
          className="image-preview-img"
          src={preview.src}
          alt={preview.alt}
          draggable={false}
          style={{ transform: `scale(${scale})` }}
          onClick={(event) => event.stopPropagation()}
        />
      </div>
    </div>
  );
}
