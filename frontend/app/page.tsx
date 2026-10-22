import CvUpload from "./components/CvUpload";
import LiveFeed from "./components/LiveFeed";
import ProfilePanel from "./components/ProfilePanel";
import { SnapshotHud } from "./components/Signals";
import TrendingCareers from "./components/TrendingCareers";
import Shell from "./components/Shell";
import SimulatorProvider from "./components/SimulatorProvider";
import { bets } from "./data/bets";

export default function Home() {
  return (
    <Shell bubbles>
      <SimulatorProvider>
      <section className="hero">
        <span className="eyebrow">AI watches the market. You grow.</span>
        <h1>
          See where your work is heading <span className="accent">before it moves.</span>
        </h1>
        <p>
          Upload your resume and Kompas maps your skills against live AI and job-market signals,
          then shows the careers that fit you and where the market is heading.
        </p>
        <SnapshotHud />
      </section>

      <CvUpload />

      <ProfilePanel />

      <TrendingCareers bets={bets} />

      <LiveFeed />

      <footer className="foot muted">
        Resources checked 20 Oct 2026. Projections are estimates based on current signals, not predictions.
        CVs are read by Gemini 2.5 Flash (Google) and never stored.
      </footer>
      </SimulatorProvider>
    </Shell>
  );
}
