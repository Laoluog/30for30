"use client";

import { RotatingPromptInput } from "@/components/rotating-prompt-input";
import { VideoBoard } from "@/components/video-board";
import { useState } from "react";

export default function Home() {
  const [selectedUrl, setSelectedUrl] = useState<string | null>(null);

  return (
    <main className="min-h-screen bg-black text-white">
      {/* subtle ESPN-ish backdrop */}
      <div className="pointer-events-none fixed inset-0 -z-10">
        <div className="absolute inset-0 bg-[radial-gradient(70%_60%_at_50%_10%,rgba(239,68,68,0.16),transparent_60%)]" />
        <div className="absolute inset-0 bg-[linear-gradient(to_bottom,rgba(255,255,255,0.06)_1px,transparent_1px)] bg-[length:100%_44px] opacity-[0.14]" />
        <div className="absolute inset-0 bg-[radial-gradient(50%_50%_at_50%_100%,rgba(239,68,68,0.10),transparent_55%)]" />
      </div>

      <section className="mx-auto flex min-h-screen w-full max-w-6xl flex-col justify-center px-5 py-14">
        <div className="mb-6 h-px w-16 bg-red-600/80 shadow-[0_0_24px_rgba(239,68,68,0.55)]" />

        <div className="grid w-full grid-cols-1 gap-6 md:grid-cols-[1.1fr_0.9fr] md:items-start">
          <div>
            <h1 className="text-balance text-4xl font-semibold leading-[1.05] tracking-tight md:text-6xl">
              30<span className="text-red-500">for</span>30 Trailer Generator
            </h1>

            <p className="mt-4 max-w-2xl text-pretty text-sm leading-6 text-white/70 md:text-base">
              Input a simple prompt and get a full ESPN 30 for 30 style trailer.
            </p>

            <RotatingPromptInput
              selectedAssetUrl={selectedUrl}
              onSelectAssetUrl={(url) => setSelectedUrl(url)}
            />
          </div>

          <div className="md:mt-2">
            <VideoBoard url={selectedUrl} onClear={() => setSelectedUrl(null)} />
          </div>
        </div>
      </section>
    </main>
  );
}
