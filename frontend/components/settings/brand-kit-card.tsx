"use client";

/**
 * The brand kit, as a settings card.
 *
 * This is where a school's identity is entered once. Everything here is
 * optional and everything degrades: a teacher who never opens this card gets
 * exactly the behaviour that existed before it, and a half-filled kit fills in
 * only the half it knows. A brand kit must never be the reason a paper cannot
 * be printed.
 *
 * Text fields save on blur rather than behind a Save button. There is no
 * multi-field invariant to enforce — each value is independent, and the API
 * patches them independently — so a button would only add a step and a way to
 * lose an edit by navigating away.
 */

import * as React from "react";
import { toast } from "sonner";
import { ImageUp, Loader2, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  deleteBrandLogo,
  fetchBrandKit,
  updateBrandKit,
  uploadBrandLogo,
  type BrandAsset,
  type BrandKit,
} from "@/lib/api-client";

export function BrandKitCard() {
  const [kit, setKit] = React.useState<BrandKit | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const [isUploading, setIsUploading] = React.useState(false);
  const [name, setName] = React.useState("");
  const [address, setAddress] = React.useState("");
  const fileRef = React.useRef<HTMLInputElement | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    fetchBrandKit()
      .then((loaded) => {
        if (cancelled) return;
        setKit(loaded);
        setName(loaded.instituteName);
        setAddress(loaded.instituteAddress);
      })
      .catch((error: any) => {
        if (!cancelled) {
          toast.error(error?.message || "Could not load your brand kit.");
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  /** Save one field, but only when it actually changed. */
  const saveField = async (
    field: "instituteName" | "instituteAddress",
    value: string,
  ) => {
    if (!kit) return;
    if (kit[field] === value) return;
    try {
      setKit(await updateBrandKit({ [field]: value }));
    } catch (error: any) {
      toast.error(error?.message || "Could not save that.");
    }
  };

  const handleUpload = async (file: File) => {
    setIsUploading(true);
    try {
      const asset = await uploadBrandLogo(file);
      setKit((prev) =>
        prev ? { ...prev, logos: [...prev.logos, asset] } : prev,
      );
      toast.success("Logo saved.");
    } catch (error: any) {
      toast.error(error?.message || "Could not upload that image.");
    } finally {
      setIsUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleDelete = async (asset: BrandAsset) => {
    try {
      await deleteBrandLogo(asset.id);
      setKit((prev) =>
        prev
          ? { ...prev, logos: prev.logos.filter((l) => l.id !== asset.id) }
          : prev,
      );
      toast.success("Logo removed.");
    } catch (error: any) {
      toast.error(error?.message || "Could not remove that logo.");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Institute branding</CardTitle>
        <CardDescription>
          Saved once and offered on every paper header, so a logo never has to
          be uploaded twice. Papers you have already made are unaffected.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-5">
        {isLoading ? (
          <div className="flex h-24 items-center justify-center">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="brand-name">Institute name</Label>
                <Input
                  id="brand-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  onBlur={() => void saveField("instituteName", name.trim())}
                  placeholder="Central Public School"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="brand-address">Address or subtitle</Label>
                <Input
                  id="brand-address"
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  onBlur={() =>
                    void saveField("instituteAddress", address.trim())
                  }
                  placeholder="CBSE Affiliation No. 000000"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label>Logos</Label>
              {kit && kit.logos.length > 0 ? (
                <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
                  {kit.logos.map((logo) => (
                    <div
                      key={logo.id}
                      className="group relative flex h-20 items-center justify-center rounded-lg border border-border bg-muted/30 p-2"
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={logo.url}
                        alt={logo.name || ""}
                        className="max-h-full max-w-full object-contain"
                      />
                      <button
                        type="button"
                        onClick={() => void handleDelete(logo)}
                        aria-label={`Remove ${logo.name || "logo"}`}
                        className="absolute right-1 top-1 rounded-full bg-destructive p-1 text-white opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
                      >
                        <Trash2 className="h-3 w-3" />
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="rounded-lg border border-dashed border-border px-3 py-5 text-center text-xs leading-relaxed text-muted-foreground">
                  No logos yet. A school crest and a board emblem can both live
                  here — papers often carry two.
                </p>
              )}

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
                className="gap-1.5"
                disabled={isUploading}
                onClick={() => fileRef.current?.click()}
              >
                {isUploading ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <ImageUp className="h-3.5 w-3.5" />
                )}
                {isUploading ? "Uploading…" : "Upload a logo"}
              </Button>
              <p className="text-xs leading-relaxed text-muted-foreground">
                PNG, JPEG, WebP or GIF, up to 4 MB. SVG is not accepted — it is
                a scriptable document, and these get embedded into exported
                files.
              </p>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
