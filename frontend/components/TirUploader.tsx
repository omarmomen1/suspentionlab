"use client";
import { useRef, useState } from "react";
import { Upload, FileText, Check, X } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import { apiFetch } from "../lib/api";

interface TirUploaderProps {
  onParsed: (coeffs: Record<string, unknown>) => void;
  onClear: () => void;
  hasCoeffs: boolean;
}

export default function TirUploader({ onParsed, onClear, hasCoeffs }: TirUploaderProps) {
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { authHeader } = useAuth();

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    setIsUploading(true);
    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await apiFetch("/parse-tir", {
        method: "POST",
        body: formData,
      });
      if (res.ok) {
        const data = await res.json();
        setUploadError(null);
        onParsed(data);
      } else {
        setUploadError("Failed to parse .tir file. Ensure it is a valid Pacejka Property File.");
      }
    } catch (err: unknown) { void err;
      setUploadError("Network error. Check connection and retry.");
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  return (
    <div className="flex flex-col gap-1.5 mt-2 p-2 bg-[#0d0d0f] border border-[#252525] rounded-lg">
      <div className="flex justify-between items-center">
        <label className="text-[11px] text-gray-400 flex items-center gap-1.5 font-semibold">
          <FileText size={12} className={hasCoeffs ? "text-emerald-400" : "text-gray-500"} />
          Pacejka .tir File
          {hasCoeffs && <Check size={10} className="text-emerald-400" />}
        </label>
        
        {hasCoeffs ? (
          <button
            type="button"
            onClick={onClear}
            aria-label="Clear Pacejka tire file"
            className="text-[10px] bg-red-950/30 text-red-400 border border-red-900/40 px-2 py-0.5 rounded flex items-center gap-1 hover:bg-red-900/50 transition-colors"
          >
            <X size={10} /> Clear
          </button>
        ) : (
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
            aria-label="Upload Pacejka tire file"
            className="text-[10px] bg-ansys-yellow text-black px-2 py-0.5 rounded flex items-center gap-1 font-bold hover:brightness-110 disabled:opacity-50 transition-all shadow-[0_0_10px_rgba(242,169,0,0.2)]"
          >
            {isUploading ? "..." : <><Upload size={10} /> Upload</>}
          </button>
        )}
      </div>
      
      <input type="file" accept=".tir,.txt" ref={fileInputRef} className="hidden" aria-label="Pacejka file input" onChange={handleUpload} />
      
      {uploadError && (
        <p role="alert" aria-live="polite" className="text-[9px] text-red-400 leading-tight mt-1">{uploadError}</p>
      )}

      {hasCoeffs ? (
        <p className="text-[9px] text-emerald-400 leading-tight">
          Custom tire coefficients loaded.
        </p>
      ) : (
        <p className="text-[9px] text-gray-400 leading-tight">
          Upload a standard Pacejka Property File (.tir) to override default tires.
        </p>
      )}
    </div>
  );
}
