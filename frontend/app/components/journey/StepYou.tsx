"use client";

import CvUpload from "../CvUpload";
import ProfilePanel from "../ProfilePanel";
import { SnapshotHud } from "../Signals";

/** Step 1: upload a CV and watch Kompas read it, match it with the market and suggest a direction. The current job
 * The Mirror needs is read from the CV (and can be changed inside the reading flow). */
export default function StepYou() {
  return (
    <>
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
    </>
  );
}
