import { JourneyProvider } from "./journey/JourneyProvider";
import { LadderProvider } from "./journey/shared";
import { ProfileProvider } from "./Profile";
import { SdgProvider } from "./Sdg";
import Sidebar from "./Sidebar";
import { SignalsProvider } from "./Signals";

export default function Shell({ children, bubbles = false }: { children: React.ReactNode; bubbles?: boolean }) {
  return (
    <ProfileProvider>
      <SdgProvider>
      <SignalsProvider>
        <JourneyProvider>
        <LadderProvider>
        <div className="shell">
          <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden>
            <defs>
              {/* bends the backdrop behind .glass (Chromium only, see layout.tsx) */}
              <filter id="liquid" x="0" y="0" width="100%" height="100%" colorInterpolationFilters="sRGB">
                <feTurbulence type="fractalNoise" baseFrequency="0.006 0.009" numOctaves="2" seed="7" result="noise" />
                <feGaussianBlur in="noise" stdDeviation="2" result="soft" />
                <feDisplacementMap in="SourceGraphic" in2="soft" scale="40" xChannelSelector="R" yChannelSelector="G" />
              </filter>
              <linearGradient id="ringGrad" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#2b3a55" />
                <stop offset="55%" stopColor="#3d9be9" />
                <stop offset="100%" stopColor="#b7a9ee" />
              </linearGradient>
            </defs>
          </svg>
          <div className="orb orb-a" aria-hidden />
          <div className="orb orb-b" aria-hidden />
          <div className="orb orb-c" aria-hidden />
          <div className="orb orb-d" aria-hidden />

          <Sidebar />

          <main className="main">
            {/* inside the scroll area so the bubbles move with the page */}
            {bubbles && (
              <>
                <div className="bubble bubble-lg" aria-hidden />
                <div className="bubble bubble-sm" aria-hidden />
              </>
            )}
            {children}
          </main>
        </div>
        </LadderProvider>
        </JourneyProvider>
      </SignalsProvider>
      </SdgProvider>
    </ProfileProvider>
  );
}
