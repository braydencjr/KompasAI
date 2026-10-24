import Journey from "./components/journey/Journey";
import ProgressSync from "./components/ProgressSync";
import Shell from "./components/Shell";
import SimulatorProvider from "./components/SimulatorProvider";

export default function Home() {
  return (
    <Shell bubbles>
      <SimulatorProvider>
        <ProgressSync />
        <Journey />
        <footer className="foot muted">
          Projections are estimates based on current signals, not predictions. Tasks from ESCO (European Commission,
          CC BY 4.0); Malaysian demand from DOSM and MyCOL. Resumes are read by Gemini 2.5 Flash (Google), or by keyword
          matching when it&apos;s unavailable, and never stored; every skill it reports must quote your resume.
        </footer>
      </SimulatorProvider>
    </Shell>
  );
}
