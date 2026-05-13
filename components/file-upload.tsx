"use client";

import React, { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, File, X, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Progress } from '@/components/ui/progress';
import { Button } from '@/components/ui/button';

interface FileUploadProps {
  onUploadComplete: (documentId: string) => void;
  projectId?: string;
}

export function FileUpload({ onUploadComplete, projectId }: FileUploadProps) {
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
      'application/pdf': ['.pdf'],
      'text/plain': ['.txt'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx']
    },
    maxFiles: 1,
    disabled: uploading
  });

  const handleUpload = async () => {
    if (!file) return;

    setUploading(true);
    setProgress(10);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('file', file);
      if (projectId) formData.append('projectId', projectId);

      // We'll use a fetch request to a route handler for uploading
      // Since server actions have size limits and complex streaming might be needed
      const response = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Upload failed');
      }

      const data = await response.json();
      
      setProgress(100);
      setSuccess(true);
      onUploadComplete(data.documentId);
    } catch (err: any) {
      console.error(err);
      setError(err.message || 'Something went wrong during upload');
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
            isDragActive ? "border-indigo-500 bg-indigo-500/5" : "border-zinc-800 hover:border-zinc-700 bg-zinc-900/50",
            uploading && "opacity-50 cursor-not-allowed"
          )}
        >
          <input {...getInputProps()} />
          <div className="h-12 w-12 rounded-full bg-zinc-800 flex items-center justify-center">
            <Upload className="h-6 w-6 text-zinc-400" />
          </div>
          <div className="text-center">
            <p className="text-zinc-200 font-medium">Click to upload or drag and drop</p>
            <p className="text-zinc-500 text-sm mt-1">PDF, TXT, or DOCX (max. 10MB)</p>
          </div>
        </div>
      ) : (
        <div className="border border-zinc-800 rounded-xl p-4 bg-zinc-900/50">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3 min-w-0">
              <div className="h-10 w-10 rounded-lg bg-zinc-800 flex items-center justify-center flex-shrink-0">
                <File className="h-5 w-5 text-indigo-400" />
              </div>
              <div className="min-w-0">
                <p className="text-zinc-200 font-medium truncate">{file.name}</p>
                <p className="text-zinc-500 text-xs">{(file.size / (1024 * 1024)).toFixed(2)} MB</p>
              </div>
            </div>
            {!uploading && !success && (
              <Button variant="ghost" size="icon" onClick={removeFile} className="text-zinc-500 hover:text-zinc-300">
                <X className="h-4 w-4" />
              </Button>
            )}
            {success && <CheckCircle2 className="h-5 w-5 text-green-500 flex-shrink-0" />}
          </div>

          {(uploading || progress > 0) && !success && !error && (
            <div className="mt-4 space-y-2">
              <div className="flex justify-between text-xs text-zinc-500">
                <span>{uploading ? "Uploading & Processing..." : "Ready"}</span>
                <span>{progress}%</span>
              </div>
              <Progress value={progress} className="h-1 bg-zinc-800" />
            </div>
          )}

          {error && (
            <div className="mt-4 flex items-center gap-2 text-red-400 text-sm bg-red-400/5 p-3 rounded-lg border border-red-400/10">
              <AlertCircle className="h-4 w-4" />
              <p>{error}</p>
            </div>
          )}

          {!uploading && !success && !error && (
            <Button onClick={handleUpload} className="w-full mt-4 bg-indigo-600 hover:bg-indigo-700 text-white">
              Process Document
            </Button>
          )}

          {uploading && (
            <Button disabled className="w-full mt-4 bg-zinc-800 text-zinc-400 flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" />
              Processing...
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
