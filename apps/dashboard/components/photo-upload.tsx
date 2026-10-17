"use client";

import { useRef, useState } from "react";
import { ImageCropDialog } from "@/components/ui/image-cropper";
import { friendlyApiError } from "@/lib/api-error";
import { useI18n } from "@/lib/i18n/provider";

interface PhotoUploadProps {
  currentUrl: string | null;
  /** BFF proxy path (no leading /api/proxy), e.g. `customers/${id}/photo`. */
  uploadPath: string;
  onUploaded: (newPhotoUrl: string) => void;
  alt: string;
  size?: number;
  /** Una foto profilo: prima di caricarla si ritaglia nel cerchio. */
  crop?: boolean;
}

/** Shared photo upload widget: shows the current photo (or a generic person
    icon if there isn't one -- never a broken image), a file picker, and a
    preview of whatever was just picked before upload completes. Reused for
    customer, promoter and product photos -- same upload mechanics, same
    "name prominent, id small below"-style fallback everywhere. */
export function PhotoUpload({ currentUrl, uploadPath, onUploaded, alt, size = 96, crop = false }: PhotoUploadProps) {
  const { t } = useI18n();
  const inputRef = useRef<HTMLInputElement>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<File | null>(null);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (crop) {
      setPicked(file);
      e.target.value = "";
      return;
    }
    void upload(file);
  }

  async function upload(file: File) {
    setError(null);
    const localPreview = URL.createObjectURL(file);
    setPreviewUrl(localPreview);
    setUploading(true);

    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`/api/proxy/${uploadPath}`, { method: "POST", body: formData });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const updated = await res.json();
      const newUrl: string | undefined = updated.photo_url ?? updated.image_url;
      if (newUrl) onUploaded(newUrl);
    } catch (err: any) {
      setError(t("acct.photo.failed"));
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  const displayUrl = previewUrl ?? currentUrl;

  return (
    <div className="flex items-center gap-4">
      <div
        className="rounded-full overflow-hidden border border-slate-200 bg-slate-100 flex items-center justify-center shrink-0"
        style={{ width: size, height: size }}
      >
        {displayUrl ? (
          // eslint-disable-next-line @next/next/no-img-element -- externally-hosted, variable-source uploaded photo
          <img src={displayUrl} alt={alt} className="w-full h-full object-cover" />
        ) : (
          <svg className="w-1/2 h-1/2 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
          </svg>
        )}
      </div>
      <div className="space-y-1">
        <input ref={inputRef} type="file" accept="image/*" onChange={handleFileChange} className="hidden" id={`photo-input-${uploadPath}`} />
        <label
          htmlFor={`photo-input-${uploadPath}`}
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-900/5 hover:bg-slate-100 border border-slate-300 text-slate-600 cursor-pointer transition"
        >
          {uploading ? t("acct.photo.uploading") : displayUrl ? t("acct.photo.change") : t("acct.photo.upload")}
        </label>
        {error && <p className="text-[11px] text-rose-400">{error}</p>}
      </div>
      {crop && <ImageCropDialog file={picked} onCancel={() => setPicked(null)} onConfirm={async (f) => { setPicked(null); await upload(f); }} />}
    </div>
  );
}
