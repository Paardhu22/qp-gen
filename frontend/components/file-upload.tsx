"use client";

import React, { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import {
  Upload,
  File,
  X,
  CheckCircle2,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { fetchForm, fetchJson } from "@/lib/api-client";
import { toast } from "sonner";

interface FileUploadProps {
  onUploadComplete: (pdfSourceId: string) => void;
}

export function FileUpload({ onUploadComplete }: FileUploadProps) {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const selectedFile = acceptedFiles[0];
    if (selectedFile) {
      setFile(selectedFile);
      setError(null);
      setSuccess(false);
      setProgress(0);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "text/plain": [".txt"],
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        [".docx"],
    },
    maxFiles: 1,
    disabled: uploading,
  });

  const handleUpload = async () => {
    if (!file) return;

    setUploading(true);
    setProgress(10);
    setError(null);

    try {
      // Try presigned direct-to-S3 upload first
      let presign: {
        url?: string;
        fields?: Record<string, string>;
        key?: string;
      } | null = null;

      try {
        presign = await fetchJson<{
          url?: string;
          fields?: Record<string, string>;
          key?: string;
        }>("/api/documents/presign", {
          method: "POST",
          body: JSON.stringify({
            name: file.name,
            content_type: file.type,
            size: file.size,
          }),
        });
      } catch {
        presign = null;
      }

      if (presign && presign.url && presign.fields && presign.key) {
        // Build form for S3 POST
        const s3form = new FormData();
        Object.entries(presign.fields).forEach(([k, v]) =>
          s3form.append(k, v as string),
        );
        s3form.append("file", file);

        const uploadRes = await fetch(presign.url, {
          method: "POST",
          body: s3form,
        });

        if (!uploadRes.ok) {
          throw new Error("Failed to upload file to storage");
        }

        // Notify backend to process the uploaded object
        const data = await fetchJson<{
          pdfSourceId: string;
          warnings?: string[];
        }>("/api/documents/confirm", {
          method: "POST",
          body: JSON.stringify({
            key: presign.key,
            name: file.name,
            content_type: file.type,
          }),
        });

        setProgress(100);
        setSuccess(true);
        if (data.warnings?.length) {
          for (const w of data.warnings) {
            toast.warning(w, { duration: 8000 });
          }
        }
        onUploadComplete(data.pdfSourceId);
        return;
      }

      // Fallback to server upload if presign is not available
      const formData = new FormData();
      formData.append("file", file);

      const data = await fetchForm<{
        pdfSourceId: string;
        warnings?: string[];
      }>("/api/documents/upload", formData);

      setProgress(100);
      setSuccess(true);
      if (data.warnings?.length) {
        for (const w of data.warnings) {
          toast.warning(w, { duration: 8000 });
        }
      }
      onUploadComplete(data.pdfSourceId);
    } catch (err: any) {
      console.error(err);
      setError(err.message || "Something went wrong during upload");
    } finally {
      setUploading(false);
    }
  };

  const removeFile = () => {
    setFile(null);
    setProgress(0);
    setError(null);
    setSuccess(false);
  };

  return (
    <div className="w-full space-y-4">
      {!file ? (
        <div
          {...getRootProps()}
          className={cn(
            "border-2 border-dashed rounded-xl p-8 transition-all cursor-pointer flex flex-col items-center justify-center gap-4",
            isDragActive
              ? "border-primary bg-primary/5"
              : "border-border hover:border-primary/50 bg-muted/50",
            uploading && "opacity-50 cursor-not-allowed",
          )}
        >
          <input {...getInputProps()} />
          <div className="h-12 w-12 rounded-full bg-muted flex items-center justify-center">
            <Upload className="h-6 w-6 text-muted-foreground" />
          </div>
          <div className="text-center">
            <p className="text-foreground font-medium">
              Click to upload or drag and drop
            </p>
            <p className="text-muted-foreground text-sm mt-1">
              PDF, TXT, or DOCX (max. 10MB)
            </p>
          </div>
        </div>
      ) : (
        <div className="border border-border rounded-xl p-4 bg-muted/50">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3 min-w-0">
              <div className="h-10 w-10 rounded-lg bg-muted flex items-center justify-center flex-shrink-0">
                <File className="h-5 w-5 text-primary" />
              </div>
              <div className="min-w-0">
                <p className="text-foreground font-medium truncate">
                  {file.name}
                </p>
                <p className="text-muted-foreground text-xs">
                  {(file.size / (1024 * 1024)).toFixed(2)} MB
                </p>
              </div>
            </div>
            {!uploading && !success && (
              <Button
                variant="ghost"
                size="icon"
                onClick={removeFile}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </Button>
            )}
            {success && (
              <CheckCircle2 className="h-5 w-5 text-green-500 flex-shrink-0" />
            )}
          </div>

          {(uploading || progress > 0) && !success && !error && (
            <div className="mt-4 space-y-2">
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>{uploading ? "Uploading & Processing..." : "Ready"}</span>
                <span>{progress}%</span>
              </div>
              <Progress value={progress} className="h-1 bg-muted" />
            </div>
          )}

          {error && (
            <div className="mt-4 flex items-center gap-2 text-red-400 text-sm bg-red-400/5 p-3 rounded-lg border border-red-400/10">
              <AlertCircle className="h-4 w-4" />
              <p>{error}</p>
            </div>
          )}

          {!uploading && !success && !error && (
            <Button
              onClick={handleUpload}
              className="w-full mt-4 bg-primary hover:bg-primary/90 text-primary-foreground"
            >
              Process Source
            </Button>
          )}

          {uploading && (
            <Button
              disabled
              className="w-full mt-4 bg-muted text-muted-foreground flex items-center gap-2"
            >
              <Loader2 className="h-4 w-4 animate-spin" />
              Processing...
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
