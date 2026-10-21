import CvMatch from "./components/CvMatch";
import TrendingCareers from "./components/TrendingCareers";
import Shell from "./components/Shell";
import UploadCard from "./components/UploadCard";
import { bets, cvMatch } from "./data/bets";

export default function Home() {
  return (
    <Shell bubbles>
      <section className="hero">
        <span className="eyebrow">AI watches the market. You grow.</span>
        <h1>
          See where your work is heading <span className="accent">before it moves.</span>
        </h1>
        <p>
          Upload your resume and Kompas maps your skills against live AI and job-market signals,
          then shows the careers that fit you and where the market is heading.
        </p>
        <div className="hud">
          <span>Snapshot <strong>2026.10.20</strong></span>
          <span>Sources <strong>06</strong></span>
          <span>Scenario <strong>Moderate</strong></span>
        </div>
      </section>

      <UploadCard />

      <CvMatch role={cvMatch} />

      <TrendingCareers bets={bets} />

      <footer className="foot muted">
        Resources checked 20 Oct 2026. Projections are estimates based on current signals, not predictions.
      </footer>
    </Shell>
  );
}
