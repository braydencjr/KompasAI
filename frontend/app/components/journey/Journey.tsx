"use client";

import JobsButton from "../JobsButton";
import { toBet } from "../../lib/adapters";
import { STEPS, useJourney } from "./JourneyProvider";
import StepBets from "./StepBets";
import StepFuture from "./StepFuture";
import StepPing from "./StepPing";
import StepRoute from "./StepRoute";
import StepYou from "./StepYou";

const COPY: Record<(typeof STEPS)[number]["id"], { title: React.ReactNode; sub: string }> = {
  you: {
    title: <>See where your work is heading <span className="accent">before it moves.</span></>,
    sub: "Upload your resume, or start with Aisyah's. Kompas reads your skills and the job you do today.",
  },
  future: { title: "Your work in 2028", sub: "Is your job safe from AI, what your skills will be worth, and the tasks behind both." },
  bets: { title: "Where your Kompas points", sub: "Upskill where you are, or switch: the fastest-growing job you fit, or the safest move." },
  route: { title: "Your learning route", sub: "An ordered plan to your chosen role, with verified courses and the evidence for every step." },
  ping: { title: "The world moved. Here's what changed for you.", sub: "Each new snapshot re-scores the market. Kompas shows what moved, why, and re-plans." },
};

const VIEWS = { you: StepYou, future: StepFuture, bets: StepBets, route: StepRoute, ping: StepPing };

export default function Journey() {
  const { step, direction, back, next, go, error, loading, data } = useJourney();
  const index = STEPS.findIndex((s) => s.id === step);
  const View = VIEWS[step];
  // the route page's header carries the job boards button for the job it leads to
  const route = step === "route" ? data?.route : undefined;
  const score = route ? data?.roles.find((x) => x.isco === route.role.isco) : undefined;

  return (
    <div className="j-journey">
      {step !== "you" && <header className={`j-head${score ? " has-action" : ""}`} key={`head-${step}`}>
        <div className="j-head-text">
        <span className="eyebrow">{index === 0 ? "AI watches the market. You grow." : `${String(index).padStart(2, "0")} · ${STEPS[index].label}`}</span>
        {step === "route" && data?.route ? (
          // the route page is named after the job it leads to
          <h1>
            <span className="j-head-kicker">{COPY.route.title}</span>
            {data.route.role.title}
          </h1>
        ) : (
          <h1>{COPY[step].title}</h1>
        )}
        <p>{COPY[step].sub}</p>
        </div>
        {score && <div className="j-head-action"><JobsButton bet={toBet("safe", score)} /></div>}
      </header>}

      {error && (
        <div className="feed-empty glass muted small">
          {error.includes("snapshot") || error.includes("fetch") ? (
            <>Can&apos;t load your journey: {error} Start the backend (<code>cd backend &amp;&amp; .venv/bin/fastapi dev app/main.py</code>).</>
          ) : error}
        </div>
      )}

      <div key={step} className={`j-stage ${direction > 0 ? "fwd" : "back"}`}>
        <View />
      </div>

      <nav className="j-nav" aria-label="Journey steps">
        <button className="btn btn-ghost" onClick={back} disabled={index === 0}>← Back</button>
        <ol className="j-dots">
          {STEPS.map((s, i) => (
            <li key={s.id}>
              <button className={i === index ? "on" : i < index ? "done" : ""} onClick={() => go(s.id)} aria-label={s.label}
                aria-current={i === index ? "step" : undefined} />
            </li>
          ))}
        </ol>
        <button className="btn btn-primary" onClick={next} disabled={index === STEPS.length - 1}>Next →</button>
      </nav>
    </div>
  );
}
