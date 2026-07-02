/**
 * ImageLightbox — full-screen image viewer with prev/next navigation.
 *
 * Usage:
 *   <ImageLightbox images={urls} initialIndex={0} onClose={() => setOpen(false)} />
 */

import { useEffect, useState, useCallback } from "react";
import { X, ChevronLeft, ChevronRight, Download, ZoomIn, ZoomOut } from "lucide-react";

interface Props {
  images: { url: string; label?: string }[];
  initialIndex?: number;
  onClose: () => void;
}

export default function ImageLightbox({ images, initialIndex = 0, onClose }: Props) {
  const [index, setIndex] = useState(initialIndex);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

  const current = images[index];

  // Reset zoom/pan when switching images
  useEffect(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, [index]);

  const prev = useCallback(() => {
    setIndex((i) => (i - 1 + images.length) % images.length);
  }, [images.length]);

  const next = useCallback(() => {
    setIndex((i) => (i + 1) % images.length);
  }, [images.length]);

  // Keyboard navigation
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft" && images.length > 1) prev();
      if (e.key === "ArrowRight" && images.length > 1) next();
      if (e.key === "+" || e.key === "=") setZoom((z) => Math.min(z + 0.25, 4));
      if (e.key === "-") setZoom((z) => Math.max(z - 0.25, 0.5));
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, prev, next, images.length]);

  // Mouse drag for panning when zoomed
  function onMouseDown(e: React.MouseEvent) {
    if (zoom <= 1) return;
    setDragging(true);
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
    e.preventDefault();
  }
  function onMouseMove(e: React.MouseEvent) {
    if (!dragging) return;
    setPan({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y });
  }
  function onMouseUp() {
    setDragging(false);
  }

  function handleDownload() {
    const a = document.createElement("a");
    a.href = current.url;
    a.download = current.label ?? `image-${index + 1}.jpg`;
    a.target = "_blank";
    a.click();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col bg-black/95"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      {/* Top bar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800 shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-white text-sm font-medium">
            {current.label ?? `Image ${index + 1}`}
          </span>
          {images.length > 1 && (
            <span className="text-gray-500 text-xs">
              {index + 1} / {images.length}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* Zoom controls */}
          <button
            onClick={() => setZoom((z) => Math.max(z - 0.25, 0.5))}
            className="p-1.5 text-gray-400 hover:text-white hover:bg-gray-800 rounded transition-colors"
            title="Zoom out (−)"
          >
            <ZoomOut size={16} />
          </button>
          <span className="text-xs text-gray-400 w-10 text-center font-mono">
            {Math.round(zoom * 100)}%
          </span>
          <button
            onClick={() => setZoom((z) => Math.min(z + 0.25, 4))}
            className="p-1.5 text-gray-400 hover:text-white hover:bg-gray-800 rounded transition-colors"
            title="Zoom in (+)"
          >
            <ZoomIn size={16} />
          </button>
          <div className="w-px h-4 bg-gray-700 mx-1" />
          <button
            onClick={handleDownload}
            className="p-1.5 text-gray-400 hover:text-white hover:bg-gray-800 rounded transition-colors"
            title="Download"
          >
            <Download size={16} />
          </button>
          <button
            onClick={onClose}
            className="p-1.5 text-gray-400 hover:text-white hover:bg-gray-800 rounded transition-colors"
            title="Close (Esc)"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      {/* Image area */}
      <div
        className="flex-1 flex items-center justify-center overflow-hidden relative"
        style={{ cursor: zoom > 1 ? (dragging ? "grabbing" : "grab") : "default" }}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
      >
        {/* Prev button */}
        {images.length > 1 && (
          <button
            onClick={(e) => { e.stopPropagation(); prev(); }}
            className="absolute left-4 z-10 p-2 bg-gray-900/80 hover:bg-gray-800 text-white rounded-full border border-gray-700 transition-colors"
          >
            <ChevronLeft size={20} />
          </button>
        )}

        <img
          src={current.url}
          alt={current.label ?? `Image ${index + 1}`}
          style={{
            transform: `scale(${zoom}) translate(${pan.x / zoom}px, ${pan.y / zoom}px)`,
            transition: dragging ? "none" : "transform 0.15s ease",
            maxWidth: "100%",
            maxHeight: "100%",
            objectFit: "contain",
            userSelect: "none",
            pointerEvents: "none",
          }}
          draggable={false}
        />

        {/* Next button */}
        {images.length > 1 && (
          <button
            onClick={(e) => { e.stopPropagation(); next(); }}
            className="absolute right-4 z-10 p-2 bg-gray-900/80 hover:bg-gray-800 text-white rounded-full border border-gray-700 transition-colors"
          >
            <ChevronRight size={20} />
          </button>
        )}
      </div>

      {/* Thumbnail strip (when multiple images) */}
      {images.length > 1 && (
        <div className="shrink-0 flex gap-2 justify-center px-4 py-3 border-t border-gray-800 overflow-x-auto">
          {images.map((img, i) => (
            <button
              key={i}
              onClick={() => setIndex(i)}
              className={`shrink-0 rounded border-2 overflow-hidden transition-colors ${
                i === index ? "border-brand-500" : "border-gray-700 hover:border-gray-500"
              }`}
            >
              <img
                src={img.url}
                alt={img.label ?? `Image ${i + 1}`}
                className="w-14 h-14 object-cover"
              />
            </button>
          ))}
        </div>
      )}

      {/* Help text */}
      <div className="shrink-0 text-center pb-2 text-xs text-gray-600">
        {zoom > 1 ? "Drag to pan · " : ""}
        {images.length > 1 ? "← → to navigate · " : ""}
        +/− to zoom · Esc to close
      </div>
    </div>
  );
}
