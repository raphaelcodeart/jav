"use client";

import { useState } from "react";
import { friendlyApiError } from "@/lib/api-error";

/** "Scarica tutto", per l'amministrazione: tutti gli allegati più un PDF
    riassuntivo del contratto e del cliente, in un file zip costruito lato
    server (`contracts/dossier.py`). */
export function ContractDossierActions({ contractId }: { contractId: string }) {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDownload() {
    setDownloading(true);
    setError(null);
    try {
      const res = await fetch(`/api/proxy/contracts/${contractId}/dossier.zip`);
      if (!res.ok) throw new Error(await friendlyApiError(res));

      // Il nome giusto ("Mario Rossi-<id>.zip") lo decide il server e viaggia
      // nel Content-Disposition: qui si legge quello, non si ricostruisce.
      // filename*= (UTF-8) ha la precedenza su filename=, che è la versione
      // ripulita per i client vecchi.
      const disposition = res.headers.get("content-disposition") ?? "";
      const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
      const plain = /filename="([^"]+)"/i.exec(disposition);
      const filename =
        (utf8?.[1] && decodeURIComponent(utf8[1])) || plain?.[1] || `contratto-${contractId}.zip`;

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      setError(err?.message || "Impossibile scaricare il fascicolo.");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <button
          onClick={handleDownload}
          disabled={downloading}
          className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl bg-brand-600/10 hover:bg-brand-600/20 border border-brand-500/20 text-brand-600 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5 5-5M12 15V3" />
          </svg>
          {downloading ? "Preparazione..." : "Scarica tutto (ZIP)"}
        </button>
      </div>

      <p className="text-[10px] text-slate-500">
        Tutti i documenti allegati più un PDF riassuntivo del contratto e del cliente.
      </p>

      {error && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
          {error}
        </div>
      )}
    </div>
  );
}
