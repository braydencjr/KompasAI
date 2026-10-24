import Radar from "../components/Radar";
import Shell from "../components/Shell";

export const metadata = { title: "AI Live Trend · Kompas" };

export default function RadarPage() {
  return (
    <Shell>
      <div className="radar relative">
        <header className="j-head">
          <span className="eyebrow">Live</span>
          <h1>AI Live Trend</h1>
        </header>
        <Radar />
      </div>
    </Shell>
  );
}
