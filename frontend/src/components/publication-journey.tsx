import { JournalIcon } from "@/components/journal-art";
export const publicationStages = [
  {title: "Prepare", icon: "file", summary: "Check scope, guidance and templates.", detail: "Review the journal scope, author requirements and manuscript template. Prepare your manuscript and supporting information."},
  {title: "Submit", icon: "mail", summary: "Upload or email, then confirm your draft.", detail: "Start online or by email when available. Sign in, verify your details and files, and acknowledge the approved declarations to formally submit."},
  {title: "Editorial checks", icon: "shield", summary: "The editorial team checks your submission.", detail: "The editorial team checks completeness and suitability. Initial assessment determines whether the manuscript proceeds to peer review."},
  {title: "Peer review", icon: "review", summary: "Reviewers assess the research.", detail: "An authorized editor coordinates reviewer input under the journal’s review policy. Reviewer recommendations inform the editorial decision."},
  {title: "Decision & revision", icon: "revision", summary: "Receive a decision and respond if requested.", detail: "The editor communicates a decision. If revisions are requested, submit your response and revised manuscript through your workspace. Review and revision may repeat."},
  {title: "Publication", icon: "book", summary: "Accepted work proceeds to publication.", detail: "Accepted articles proceed through production and readiness checks. Only explicitly published articles in published issues appear in the public archive."},
] as const;
export function PublicationJourney({variant}: {variant: "compact" | "detailed"}) {
  if (variant === "compact") return <ol className="publication-journey journey-strip" aria-label="Publishing journey">{publicationStages.map((stage,index)=><li key={stage.title}><span className="journey-strip__top"><JournalIcon name={stage.icon} size={20}/><span aria-label={`Step ${index+1}`}>{String(index+1).padStart(2,"0")}</span></span><h3>{stage.title}</h3></li>)}</ol>;
  return <ol className={`publication-journey publication-journey--${variant} journey-visual`}>{publicationStages.map((stage, index) => <li className="publication-journey__stage" key={stage.title}><div className="journey-stage-top"><span className="journey-icon"><JournalIcon name={stage.icon} size={24}/></span><span className="journey-step">STEP {String(index + 1).padStart(2, "0")}</span>{index < 5 && <JournalIcon name="arrow" className="journey-connector"/>}</div><div><h3>{stage.title}</h3><p>{stage.detail}</p></div></li>)}</ol>;
}
