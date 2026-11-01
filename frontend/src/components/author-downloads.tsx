import { JournalIcon } from "@/components/journal-art";
import { authorResources } from "@/lib/author-resources";

export function AuthorDownloads({ compact = false, heading = "Author downloads" }: { compact?: boolean; heading?: string }) {
  return (
    <section className={`author-downloads${compact ? " author-downloads--compact" : ""}`} aria-labelledby="author-downloads-title">
      <div className="author-downloads__heading">
        <div>
          <p className="eyebrow">READY TO USE</p>
          <h2 id="author-downloads-title">{heading}</h2>
        </div>
        <span>{authorResources.length} files</span>
      </div>
      <div className="author-downloads__grid">
        {authorResources.map((item) => (
          <a className="author-download" href={item.href} download key={item.id}>
            <span className="author-download__icon"><JournalIcon name="file" size={18} /></span>
            <span className="author-download__copy">
              <strong>{item.shortTitle}</strong>
              {!compact && <small>{item.description}</small>}
              <span>{item.format} · Download</span>
            </span>
            <JournalIcon name="download" size={14} />
          </a>
        ))}
      </div>
    </section>
  );
}
