"use client";

import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type StepStatus = "pending" | "active" | "done" | "error";
type StepKey = "script" | "shots" | "resolving" | "ready";

const NBA_EXEMPLAR_PROMPTS = [
  "What happens when LeBron’s body says “enough”… but the mission isn’t finished?",
  "Michael Jordan, the second three-peat, and the last dance nobody believed was real.",
  "Steph Curry didn’t just change the shot. He changed the belief.",
  "Kobe Bryant: the obsession, the doubts, and the final chapter in purple and gold.",
  "Kevin Durant, burner phones, and a decision that split a basketball universe.",
  "Shaq and Kobe: two supernovas, one locker room, and a dynasty on the edge.",
  "Giannis: the miles before the MVP… and the one promise he refused to break.",
  "Allen Iverson — practice jokes, bruises, and a city that finally felt seen.",
  "Jokic — the quiet MVP who treats greatness like a day job.",
  "Tim Duncan: no hype, no flash… just winning until it felt inevitable.",
  "Luka: a 19-year-old smile, a left hand, and defenders chasing ghosts.",
  "Magic vs Bird — the rivalry that saved a league and changed the TV era.",
  "Jimmy Butler: “You didn’t pick me.” So he picked a fight with the whole league.",
  "Hakeem’s footwork, a stolen spotlight, and the ring that proved everything.",
  "Jayson Tatum and the weight of a jersey that expects banners, not excuses.",
  "Dwyane Wade: the Finals that turned a young star into a force of nature.",
  "Ja Morant: flying too close to the sun when the whole world is watching.",
  "Dirk Nowitzki: one run, one ring, and a decade of doubt erased in June.",
  "Kawhi Leonard. No speeches. No noise. Just the moments that matter.",
  "One Finals. One shot. One superstar learning what pressure costs. (Damian Lillard)",
  "The year Anthony Edwards stopped being “next” and started being “now.”",
  "Kevin Garnett: the fire, the loyalty, and the one year it all finally clicked.",
  "Kyrie Irving: magic handles, messy headlines, and the price of being misunderstood.",
  "Steve Nash: two MVPs, no ring — and the offense that arrived too early.",
  "Joel Embiid’s body vs his dream — a season told in pain, jokes, and dominance.",
  "Kareem: skyhooks, silence, and the greatest points total the sport has ever seen.",
  "Nikola Jokic goes home. The league keeps calling. He doesn’t pick up.",
] as const;

export function RotatingPromptInput() {
  const exemplars = useMemo(() => NBA_EXEMPLAR_PROMPTS, []);
  const [value, setValue] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const [idx, setIdx] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<any>(null);
  const [steps, setSteps] = useState<Record<StepKey, StepStatus>>({
    script: "pending",
    shots: "pending",
    resolving: "pending",
    ready: "pending",
  });

  useEffect(() => {
    if (isFocused) return;
    if (value.trim().length > 0) return;

    const id = window.setInterval(() => {
      setIdx((i) => (i + 1) % exemplars.length);
    }, 2400);

    return () => window.clearInterval(id);
  }, [exemplars.length, isFocused, value]);

  function resetSteps() {
    setSteps({ script: "pending", shots: "pending", resolving: "pending", ready: "pending" });
  }

  async function onSubmit() {
    const prompt = value.trim();
    if (!prompt) return;

    setIsSubmitting(true);
    setError(null);
    setData(null);
    resetSteps();
    setSteps((s) => ({ ...s, script: "active" }));

    try {
      const baseUrl =
        process.env.NEXT_PUBLIC_BACKEND_URL?.replace(/\/$/, "") ??
        "http://127.0.0.1:5000";

      // Call #1: get the script + planned shots quickly.
      const res = await fetch(`${baseUrl}/generate_video`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt,
          resolve: false,
        }),
      });

      if (!res.ok) {
        const text = await res.text().catch(() => "");
        throw new Error(
          text ? `Request failed (${res.status}): ${text}` : `Request failed (${res.status})`,
        );
      }

      const contentType = res.headers.get("content-type") ?? "";
      const genData = contentType.includes("application/json")
        ? await res.json()
        : await res.text();

      setSteps((s) => ({ ...s, script: "done", shots: "done", resolving: "active" }));

      // Call #2: resolve shots.
      const shots = genData?.shots ?? [];
      const res2 = await fetch(`${baseUrl}/resolve_shots`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ shots }),
      });
      if (!res2.ok) {
        const text = await res2.text().catch(() => "");
        throw new Error(
          text ? `Resolver failed (${res2.status}): ${text}` : `Resolver failed (${res2.status})`,
        );
      }
      const ct2 = res2.headers.get("content-type") ?? "";
      const resolveData = ct2.includes("application/json") ? await res2.json() : await res2.text();

      setData({ ...genData, ...resolveData });
      setSteps((s) => ({ ...s, resolving: "done", ready: "done" }));
      // Optionally clear input after success:
      // setValue("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
      setSteps((s) => {
        const next = { ...s };
        // mark the first non-done step as error
        (["script", "shots", "resolving", "ready"] as StepKey[]).some((k) => {
          if (next[k] !== "done") {
            next[k] = "error";
            return true;
          }
          return false;
        });
        return next;
      });
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form
      className="mt-10"
      onSubmit={(e) => {
        e.preventDefault();
        void onSubmit();
      }}
    >
      <div className="group relative">
        <div className="pointer-events-none absolute -inset-0.5 rounded-full bg-gradient-to-r from-red-600/0 via-red-600/35 to-red-600/0 opacity-70 blur-sm transition-opacity group-focus-within:opacity-100" />
        <div className="relative flex items-center gap-2 rounded-full border border-white/10 bg-zinc-950/70 px-3 py-2 shadow-[0_20px_80px_-40px_rgba(239,68,68,0.45)] backdrop-blur">
          <Input
            name="prompt"
            autoComplete="off"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            placeholder={exemplars[idx]}
            className="h-12 rounded-full border-0 bg-transparent px-4 text-base text-white placeholder:text-white/35 shadow-none focus-visible:ring-0"
          />
          <Button
            type="submit"
            disabled={isSubmitting || value.trim().length === 0}
            className="h-12 rounded-full bg-red-600 px-6 text-sm font-semibold text-white shadow-sm hover:bg-red-500 focus-visible:ring-2 focus-visible:ring-red-500/50"
          >
            {isSubmitting ? "Generating..." : "Generate"}
          </Button>
        </div>
      </div>

      <p className="mt-5 text-xs text-white/45">
        Keep it short. One sentence is enough.
      </p>

      <div className="mt-3 grid gap-1 text-xs">
        {(
          [
            ["script", "Script generated"],
            ["shots", "Shots planned"],
            ["resolving", "Shots resolving"],
            ["ready", "Ready"],
          ] as const
        ).map(([key, label]) => {
          const status = steps[key];
          const dotClass =
            status === "done"
              ? "bg-emerald-500/90"
              : status === "active"
                ? "bg-red-500/90 animate-pulse"
                : status === "error"
                  ? "bg-red-300/90"
                  : "bg-white/20";
          const textClass =
            status === "done"
              ? "text-white/70"
              : status === "active"
                ? "text-white/80"
                : status === "error"
                  ? "text-red-200/90"
                  : "text-white/40";
          return (
            <div key={key} className={`flex items-center gap-2 ${textClass}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${dotClass}`} />
              <span>{label}</span>
            </div>
          );
        })}
      </div>

      {error ? (
        <p className="mt-2 text-xs text-red-300/90">{error}</p>
      ) : null}

      {/* temporary: keep the response around for debugging / wiring up the next UI step */}
      {data ? (
        <p className="mt-2 text-xs text-white/35">Script received.</p>
      ) : null}
    </form>
  );
}


