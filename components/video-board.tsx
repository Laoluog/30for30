"use client";

import { Button } from "@/components/ui/button";

function isLikelyHttpUrl(url: string) {
  return /^https?:\/\//i.test(url);
}

export function VideoBoard({
  url,
  title = "Video Board",
  onClear,
}: {
  url: string | null;
  title?: string;
  onClear?: () => void;
}) {
  const canPlay = typeof url === "string" && isLikelyHttpUrl(url);

  return (
    // Hard-cap the entire board (header + video + URL) to 25vh x 25vh.
    <section className="w-full max-w-[100vh]">
      <div className="flex h-[50vh] flex-col overflow-hidden rounded-2xl border border-white/10 bg-zinc-950/60 p-3 backdrop-blur">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[11px] uppercase tracking-wide text-white/40">{title}</p>
            <p className="text-sm font-semibold text-white">Preview</p>
          </div>
          <div className="flex items-center gap-2">
            {url ? (
              <Button
                type="button"
                variant="secondary"
                className="h-8 rounded-full border border-white/10 bg-white/5 px-3 text-xs text-white/80 hover:bg-white/10"
                onClick={() => {
                  if (typeof navigator !== "undefined" && navigator.clipboard) {
                    void navigator.clipboard.writeText(url);
                  }
                }}
              >
                Copy URL
              </Button>
            ) : null}
            {url && onClear ? (
              <Button
                type="button"
                variant="secondary"
                className="h-8 rounded-full border border-white/10 bg-white/5 px-3 text-xs text-white/80 hover:bg-white/10"
                onClick={onClear}
              >
                Clear
              </Button>
            ) : null}
          </div>
        </div>

        <div className="mt-3 flex-1 overflow-hidden rounded-xl border border-white/10 bg-black/50">
          <div className="relative h-full w-full">
            {canPlay ? (
              <video
                key={url ?? "empty"}
                controls
                playsInline
                preload="metadata"
                className="absolute inset-0 h-full w-full bg-black object-contain"
                src={url ?? undefined}
              />
            ) : (
              <div className="absolute inset-0 flex items-center justify-center p-6 text-center text-xs text-white/50">
                {url
                  ? "Select a valid http(s) video URL to preview it here."
                  : "No video selected yet. Click an asset_url to load it here."}
              </div>
            )}
          </div>
        </div>

        <div className="mt-2 max-h-10 overflow-auto rounded-lg border border-white/10 bg-black/30 p-2 font-mono text-[10px] text-white/65">
          <span className="break-all">{url ?? "—"}</span>
        </div>
      </div>
    </section>
  );
}


