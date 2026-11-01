import type { ReactNode } from "react";
import { authorNextAction, manuscriptPhases, phaseForStatus, readableStatus, reviewerNextAction } from "@/lib/manuscript-progress";

type Props = {
  reference?: string;
  title?: string;
  status?: string;
  nextAction?: string;
  displayStatus?:string;
  roundNumber?: number;
  scope?: "manuscript" | "review";
  children?: ReactNode;
};

export function ManuscriptProgress({ reference, title, status, displayStatus, nextAction, roundNumber, scope = "manuscript", children }: Props) {
  const review = scope === "review";
  const ownReviewAction = reviewerNextAction(status);
  const phase = !review && displayStatus?.startsWith("Reviews received") ? "decision" : review ? ownReviewAction ? "review" : undefined : phaseForStatus(status);
  const closed = !review && (status === "declined" || status === "withdrawn");
  const known = !!phase || closed;
  const action = known ? nextAction ?? (review ? ownReviewAction : authorNextAction(status)) : undefined;
  const statusText = status ? `${review ? "Assignment: " : ""}${readableStatus(status)}` : "Select a paper to see its progress.";
  const phaseLabel = manuscriptPhases.find(item => item.id === phase)?.label;
  const reviewSteps = [
    { label: "Invitation", current: status === "invited" },
    { label: "Conflict resolution", current: status === "conflict_reported" },
    { label: "Prepare review", current: status === "accepted" },
    { label: "Report submitted", current: status === "completed" },
  ];
  return <section className="manuscript-progress" aria-label="Manuscript progress">
    <div className="manuscript-progress__heading">
      <div><p className="eyebrow">{review ? "Your part in the manuscript journey" : "Manuscript journey"}</p>
        <h2>{reference ? `Paper ID: ${reference}` : title ? "New manuscript" : "Paper progress"}</h2>
        {title && <p className="manuscript-progress__title">{title}</p>}
      </div>
      {status && <span className={`manuscript-progress__status${closed ? " manuscript-progress__status--closed" : ""}`}>{displayStatus ?? statusText}</span>}
    </div>
    <ol className="manuscript-progress__phases" aria-label={review ? "Manuscript lifecycle: your task phase" : "Manuscript lifecycle"}>
      {manuscriptPhases.map((item, index) => <li key={item.id} aria-current={item.id === phase ? "step" : undefined}>
        <span className="manuscript-progress__number" aria-hidden="true">{index + 1}</span>
        <span>{item.label}{item.id === phase && <small>{review ? "Your task phase" : "Current"}</small>}</span>
      </li>)}
    </ol>
    <div className="manuscript-progress__next" role="status" aria-live="polite" aria-atomic="true">
      <strong>{closed ? `Workflow closed: ${readableStatus(status!)}` : phaseLabel ? `${review ? "Your task phase" : "Current phase"}: ${phaseLabel}` : statusText}</strong>
      {roundNumber !== undefined && <span>Review round {roundNumber}</span>}
      {!review && displayStatus?.startsWith("Reviews received") ? <p>{nextAction && !nextAction.includes("under review") ? nextAction : "The editorial team is considering the reports. Wait for the decision letter before taking action."}</p> : action && <p>{action}</p>}
    </div>
    {review && known && <ol className="manuscript-preparation" aria-label="Your review steps">{reviewSteps.map(step => <li key={step.label} aria-current={step.current ? "step" : undefined}>{step.label}{step.current && <span>Current</span>}</li>)}</ol>}
    {review && <p className="form-help">This shows your assignment. Later editorial decisions and other reviewers' work remain private.</p>}
    {!review && (status === "revision_requested" || status === "resubmitted" || (roundNumber ?? 1) > 1) && <p className="manuscript-progress__revision">↶ Revisions return to editorial checks and may include another peer review.</p>}
    {children}
  </section>;
}
