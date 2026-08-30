"use client";

/**
 * Choosing the logo that goes on a paper's masthead.
 *
 * The point of this dialog is the *order* of what it offers. A school uses one
 * crest on every paper it prints, so the saved brand logos come first and
 * uploading is the fallback — not the other way round. That is the whole
 * difference between "attach a file to this document" and "use our logo", and
 * it is why the brand kit exists at all.
 *
 * An upload made here is saved to the brand kit rather than to this one
 * document, so the second paper never asks again.
 */

import * as React from "react";
import { toast } from "sonner";
import { Check, Image as ImageIcon, ImageUp, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  fetchBrandKit,
  uploadBrandLogo,
  type BrandAsset,
} from "@/lib/api-client";
import { resolveFigureSrc } from "@/components/editor/extensions/float-image";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

/** Printed widths, in px on the 794px A4 page. */
const SIZES: { label: string; width: number }[] = [
  { label: "Small", width: 48 },
  { label: "Medium", width: 72 },
  { label: "Large", width: 104 },
];

interface Props {
  currentUrl: string;
  width: number;
  align: "left" | "right";
  onClose: () => void;
  onApply: (attrs: {
    logoUrl: string;
    logoWidth: number;
    logoAlign: "left" | "right";
  }) => void;
}

export function HeaderLogoPicker({
  currentUrl,
  width,
  align,
  onClose,
  onApply,
}: Props) {
  const [logos, setLogos] = React.useState<BrandAsset[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [isUploading, setIsUploading] = React.useState(false);
  const [selectedUrl, setSelectedUrl] = React.useState(currentUrl);
  const [selectedWidth, setSelectedWidth] = React.useState(width);
  const [selectedAlign, setSelectedAlign] = React.useState(align);
  const [failedImages, setFailedImages] = React.useState<Set<string>>(new Set());
  const fileRef = React.useRef<HTMLInputElement | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    fetchBrandKit()
      .then((kit) => {
        if (!cancelled) setLogos(kit.logos);
      })
      .catch(() => {
        // An unreachable brand kit still leaves upload working, which is the
        // path that mattered before any of this existed. Not worth a toast on
        // top of a dialog the teacher just opened.
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleUpload = async (file: File) => {
    setIsUploading(true);
    try {
      const asset = await uploadBrandLogo(file);
      // Saved to the brand kit, not to this document — so the next paper
      // already has it.
      setLogos((prev) => [...prev, asset]);
      setSelectedUrl(asset.url);
      toast.success("Saved to your brand kit.");
    } catch (error: any) {
      toast.error(error?.message || "Could not upload that image.");
    } finally {
      setIsUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  // The picker lives inside the TipTap node view, so it sits under
  // `.document-editor` in the DOM and inherits the *paper's* typography —
  // Times New Roman at 12pt in black. Right for the sheet, wrong for a dialog,
  // so the root re-asserts the app's UI font and text colour.
  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center p-4 font-sans text-sm text-foreground"
      contentEditable={false}
    >
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      <div className="relative z-10 w-full max-w-md rounded-2xl border border-border bg-background p-5 shadow-2xl">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold">Institute logo</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Pick one you have saved, or upload a new one.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="mt-4">
          {isLoading ? (
            <div className="flex h-24 items-center justify-center">
              <Spinner className="text-muted-foreground" />
            </div>
          ) : logos.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border px-3 py-5 text-center text-xs leading-relaxed text-muted-foreground">
              No logos saved yet. Upload one and it will be here for every
              paper you make after this.
            </p>
          ) : (
            <div className="grid grid-cols-3 gap-2.5 max-h-56 overflow-y-auto pr-0.5">
              {logos.map((logo) => {
                const active = logo.url === selectedUrl;
                const resolvedSrc = resolveFigureSrc(logo.url);
                const isFailed = failedImages.has(logo.id);
                return (
                  <button
                    key={logo.id}
                    type="button"
                    onClick={() => setSelectedUrl(logo.url)}
                    className={cn(
                      "group relative flex flex-col items-center justify-between h-24 rounded-xl border bg-muted/20 p-2 transition-all hover:bg-muted/40",
                      active
                        ? "border-primary bg-primary/5 ring-2 ring-primary/30"
                        : "border-border hover:border-primary/40",
                    )}
                  >
                    <div className="flex flex-1 w-full items-center justify-center overflow-hidden">
                      {isFailed ? (
                        <ImageIcon className="h-7 w-7 text-muted-foreground/50" />
                      ) : (
                        /* eslint-disable-next-line @next/next/no-img-element */
                        <img
                          src={resolvedSrc}
                          alt=""
                          onError={() =>
                            setFailedImages((prev) => new Set(prev).add(logo.id))
                          }
                          className="max-h-14 max-w-full object-contain transition-transform group-hover:scale-105"
                        />
                      )}
                    </div>
                    <span className="mt-1 w-full truncate text-center text-[10px] text-muted-foreground">
                      {logo.name || "Logo"}
                    </span>
                    {active ? (
                      <span className="absolute right-1.5 top-1.5 rounded-full bg-primary p-0.5 text-primary-foreground shadow-xs">
                        <Check className="h-3 w-3" />
                      </span>
                    ) : null}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <input
          ref={fileRef}
          type="file"
          accept="image/png,image/jpeg,image/webp,image/gif"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void handleUpload(file);
          }}
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-3 w-full gap-1.5"
          disabled={isUploading}
          onClick={() => fileRef.current?.click()}
        >
          {isUploading ? (
            <Spinner />
          ) : (
            <ImageUp className="h-3.5 w-3.5" />
          )}
          {isUploading ? "Uploading…" : "Upload a logo"}
        </Button>

        {selectedUrl ? (
          <div className="mt-4 space-y-3 border-t border-border pt-4">
            <div className="flex items-center gap-2">
              <span className="w-12 text-xs text-muted-foreground">Size</span>
              <div className="flex gap-1.5">
                {SIZES.map((size) => (
                  <button
                    key={size.label}
                    type="button"
                    onClick={() => setSelectedWidth(size.width)}
                    className={cn(
                      "rounded-md px-2 py-1 text-xs transition-colors",
                      selectedWidth === size.width
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {size.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span className="w-12 text-xs text-muted-foreground">Side</span>
              <div className="flex gap-1.5">
                {(["left", "right"] as const).map((side) => (
                  <button
                    key={side}
                    type="button"
                    onClick={() => setSelectedAlign(side)}
                    className={cn(
                      "rounded-md px-2 py-1 text-xs capitalize transition-colors",
                      selectedAlign === side
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {side}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : null}

        <div className="mt-5 flex items-center justify-between gap-2">
          {currentUrl ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="text-destructive hover:text-destructive"
              onClick={() =>
                onApply({
                  logoUrl: "",
                  logoWidth: selectedWidth,
                  logoAlign: selectedAlign,
                })
              }
            >
              Remove from paper
            </Button>
          ) : (
            <span />
          )}
          <div className="flex items-center gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={onClose}>
              Cancel
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={!selectedUrl}
              onClick={() =>
                onApply({
                  logoUrl: selectedUrl,
                  logoWidth: selectedWidth,
                  logoAlign: selectedAlign,
                })
              }
            >
              Use this
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
