import { API_URL } from "./kompas";

/** A Sustainable Development Goal a skill or a job contributes to, and why. */
export type SdgTagData = {
  sdg: number;
  name: string;
  /** the UN target the link rests on, like "8.5" */
  target?: string | null;
  /** how this skill or job contributes, in a sentence */
  rationale?: string | null;
  /** curated: Kompas's own mapping; ai: suggested by the AI; default: a general link */
  origin?: "curated" | "ai" | "default";
};

export const SDG_NAMES: Record<number, string> = {
  1: "No poverty", 2: "Zero hunger", 3: "Good health and well-being", 4: "Quality education", 5: "Gender equality",
  6: "Clean water and sanitation", 7: "Affordable and clean energy", 8: "Decent work and economic growth",
  9: "Industry, innovation and infrastructure", 10: "Reduced inequalities", 11: "Sustainable cities and communities",
  12: "Responsible consumption and production", 13: "Climate action", 14: "Life below water", 15: "Life on land",
  16: "Peace, justice and strong institutions", 17: "Partnerships for the goals",
};

// the UN's official colour for each goal
export const SDG_COLORS: Record<number, string> = {
  1: "#E5243B", 2: "#DDA63A", 3: "#4C9F38", 4: "#C5192D", 5: "#FF3A21", 6: "#26BDE2", 7: "#FCC30B", 8: "#A21942",
  9: "#FD6925", 10: "#DD1367", 11: "#FD9D24", 12: "#BF8B2E", 13: "#3F7E44", 14: "#0A97D9", 15: "#56C02B",
  16: "#00689D", 17: "#19486A",
};

function luminance(hex: string) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

const WHITE_AT_AA = 0.1833;      // the lightest colour white text still reads on: contrast 4.5 to 1 (WCAG AA)
const shades = new Map<number, string>();

// The UN's yellow, gold and orange goals would all turn the same brown if they were just darkened for white text, so
// these five keep their own hue: each is dark enough for white text (contrast 4.7 to 6.3) and still tells apart.
const HAND_PICKED: Record<number, string> = { 2: "#9A6B00", 7: "#7A7300", 9: "#C8431A", 11: "#B05A0A", 12: "#7B5A33" };

/** The goal's colour for a tag with white text: the UN's colour, darkened only as far as it takes for the white text
 * to be easy to read (the deep goals keep their official colour). */
export function goalBg(sdg: number): string {
  if (HAND_PICKED[sdg]) return HAND_PICKED[sdg];
  const hit = shades.get(sdg);
  if (hit) return hit;
  const base = SDG_COLORS[sdg] ?? "#555555";
  const rgb = [1, 3, 5].map((i) => parseInt(base.slice(i, i + 2), 16));
  let out = base;
  for (let t = 0; t <= 0.7; t += 0.02) {
    out = "#" + rgb.map((c) => Math.round(c * (1 - t)).toString(16).padStart(2, "0")).join("");
    if (luminance(out) <= WHITE_AT_AA) break;
  }
  shades.set(sdg, out);
  return out;
}

/** every tag's text is white */
export const ON_GOAL = "#ffffff";

export const goalUrl = (sdg: number) => `https://sdgs.un.org/goals/goal${sdg}`;

// ---------- tags for skills and jobs the page didn't arrive with, asked for in one batch ----------

type Kind = "skill" | "role";
const cache = new Map<string, SdgTagData[]>();
const settled = new Set<string>();       // asked for already (answered or not): never asked twice
const queue = new Map<string, { kind: Kind; id: string }>();
const listeners = new Set<() => void>();
let timer: ReturnType<typeof setTimeout> | null = null;

const keyOf = (kind: Kind, id: string) => `${kind}:${id}`;
export const readSdgTags = (kind: Kind, id: string) => cache.get(keyOf(kind, id));
export const sdgSettled = (kind: Kind, id: string) => settled.has(keyOf(kind, id));
export function subscribeSdg(fn: () => void) {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

const attempts = new Map<string, number>();
const RETRY_MS = [2000, 6000, 15000];      // a server that is starting, or briefly down, gets three more tries

async function flush() {
  timer = null;
  const batch = [...queue.values()].slice(0, 40);
  batch.forEach((i) => queue.delete(keyOf(i.kind, i.id)));
  if (queue.size) timer = setTimeout(flush, 0);
  let answered = false;
  try {
    const res = await fetch(`${API_URL}/sdg/tags`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ items: batch }),
    });
    if (res.ok) {
      for (const [k, v] of Object.entries((await res.json()).tags as Record<string, SdgTagData[]>)) cache.set(k, v);
      answered = true;
    }
  } catch {
    // not reachable: tried again below
  }
  for (const i of batch) {
    const k = keyOf(i.kind, i.id);
    const n = attempts.get(k) ?? 0;
    if (answered || n >= RETRY_MS.length) {
      settled.add(k);                       // answered (an id the server doesn't know gets no tag), or out of tries
    } else {
      attempts.set(k, n + 1);
      setTimeout(() => {
        queue.set(k, i);
        timer ??= setTimeout(flush, 0);
      }, RETRY_MS[n]);
    }
  }
  listeners.forEach((fn) => fn());
}

export function wantSdgTags(kind: Kind, id: string) {
  const k = keyOf(kind, id);
  if (cache.has(k) || settled.has(k) || queue.has(k)) return;
  queue.set(k, { kind, id });
  timer ??= setTimeout(flush, 40);
}
