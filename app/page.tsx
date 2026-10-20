import CvMatch from "./components/CvMatch";
import TrendingCareers from "./components/TrendingCareers";
import Shell from "./components/Shell";
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

      <section className="upload glass">
        <div className="upload-icon">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden>
            <path d="M12 16V4m0 0-4 4m4-4 4 4M5 20h14" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <div className="upload-text">
          <h3>Upload your resume</h3>
          <p>PDF or DOCX, up to 5 MB. We never use age, gender or photos.</p>
        </div>
        <div className="upload-actions">
          <button className="btn btn-ghost">Try a sample</button>
          <button className="btn btn-primary">Upload file</button>
        </div>
      </section>

      <CvMatch role={cvMatch} />

      <TrendingCareers bets={bets} />

      <footer className="foot muted">
        Resources checked 20 Oct 2026. Projections are estimates based on current signals, not predictions.
      </footer>
    </Shell>
  );
}
