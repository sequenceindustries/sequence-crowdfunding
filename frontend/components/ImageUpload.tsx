"use client";
import { useRef, useState } from "react";
import { getCsrf } from "@/lib/api";

interface Props {
  label: string;
  /** URL of the image to preview (a /api/public/images/<token> URL). */
  previewUrl?: string | null;
  /** Called when an image is successfully uploaded; receives the public token. */
  onUploaded: (token: string) => void;
  /** Called when the user removes the existing image. */
  onRemoved: () => void;
  /** POST endpoint for upload, e.g. /api/campaigns/3/cover-image */
  uploadUrl: string;
  /** DELETE endpoint, e.g. /api/campaigns/3/cover-image */
  deleteUrl: string;
}

export default function ImageUpload({ label, previewUrl, onUploaded, onRemoved, uploadUrl, deleteUrl }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("image", file);
      const headers: Record<string, string> = {};
      const csrf = getCsrf();
      if (csrf) headers["X-CSRF-Token"] = csrf;
      const r = await fetch(uploadUrl, { method: "POST", headers, body: fd, credentials: "same-origin" });
      const data = await r.json();
      if (!r.ok) {
        setError(data.message ?? "Upload failed. Please try again.");
      } else {
        onUploaded(data.token);
      }
    } catch {
      setError("Upload failed. Check your connection and try again.");
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function handleRemove() {
    setBusy(true);
    setError(null);
    try {
      const headers: Record<string, string> = {};
      const csrf = getCsrf();
      if (csrf) headers["X-CSRF-Token"] = csrf;
      await fetch(deleteUrl, { method: "DELETE", headers, credentials: "same-origin" });
      onRemoved();
    } catch {
      setError("Could not remove the image. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack" style={{ gap: "0.5rem" }}>
      <label style={{ fontWeight: 500 }}>{label}</label>
      {previewUrl && (
        <div style={{ position: "relative", display: "inline-block" }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={previewUrl}
            alt={label}
            style={{ maxWidth: 240, maxHeight: 160, borderRadius: 6, border: "1px solid var(--border, #e0e0e0)", objectFit: "cover" }}
          />
        </div>
      )}
      {error && <p className="alert alert-error" style={{ margin: 0 }}>{error}</p>}
      <div className="row" style={{ gap: "0.5rem", flexWrap: "wrap" }}>
        <label className="btn btn-secondary" style={{ cursor: "pointer" }}>
          {busy ? "Uploading…" : previewUrl ? "Replace image" : "Upload image"}
          <input
            ref={inputRef}
            type="file"
            accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp"
            style={{ display: "none" }}
            onChange={handleFile}
            disabled={busy}
          />
        </label>
        {previewUrl && (
          <button className="btn btn-secondary" onClick={handleRemove} disabled={busy} type="button">
            Remove
          </button>
        )}
      </div>
      <p className="muted" style={{ fontSize: "0.8rem", margin: 0 }}>
        PNG, JPG or WebP · max 5 MB
      </p>
    </div>
  );
}
