"use client";
import Link from "next/link";
import {DemoBadge,PublicLoadError,PublicPageLayout} from "@/components/public-site";
import {demoIssues,type PublicIssue} from "@/lib/demo-content";
import {formatPublicDate as formatDate} from "@/lib/public-format";
import {usePublicCollection} from "@/lib/use-public-collection";

type IssueGroup={key:string;volume:PublicIssue["volume"];issues:PublicIssue[]};
function groupIssues(items:PublicIssue[]){const groups=new Map<string,IssueGroup>();for(const issue of items){const key=issue.volume?`${issue.volume.year}-${issue.volume.number}`:"unassigned",existing=groups.get(key);if(existing)existing.issues.push(issue);else groups.set(key,{key,volume:issue.volume,issues:[issue]});}return [...groups.values()];}

export default function IssuesPage(){const {items,loading,error,reload}=usePublicCollection("/public/issues",demoIssues,"Published issues could not be loaded."),groups=groupIssues(items),latest=items.reduce<PublicIssue|null>((current,item)=>!item.published_at?current:!current?.published_at||Date.parse(item.published_at)>Date.parse(current.published_at)?item:current,null);
 return <PublicPageLayout eyebrow="Journal archive" title="Issues & archive" activeHref="/issues" breadcrumb="Issues & archive">
  <p className="muted-copy archive-intro">Browse published work by volume and issue. Expand an issue to see its articles.</p>
  {loading&&<p className="notice-message" role="status">Loading published issues…</p>}{!groups.length&&!loading&&!error&&<p className="notice-message" role="status">No issue has been published yet.</p>}
  {!error&&!loading&&groups.map(group=><details className="public-volume-group public-volume-group--compact" key={group.key} open={group.issues.some(issue=>issue.id===latest?.id)}><summary className="public-volume-group__header"><span><span className="eyebrow">Journal volume</span><strong id={`volume-${group.key}`}>{group.volume?`Volume ${group.volume.number} · ${group.volume.year}`:"Other published issues"}</strong></span><span className="public-volume-group__count">{group.issues.length} {group.issues.length===1?"issue":"issues"}</span></summary>
   <div className="public-volume-group__issues">{group.issues.map(issue=>{const date=formatDate(issue.published_at);return <details className={`public-issue-row${issue.id===latest?.id?" public-issue-row--latest":""}`} key={issue.id} id={`issue-${issue.id}`} open={issue.id===latest?.id}><summary><span className="public-card__meta">{issue.id===latest?.id&&!issue.demo&&<span className="public-latest-label">Latest</span>}{issue.demo?<><DemoBadge/> Issue {issue.number}</>:<>Issue {issue.number}{date?` · ${date}`:""}</>}</span><strong>{issue.title||`Issue ${issue.number}`}</strong><span>{issue.articles.length} {issue.articles.length===1?"article":"articles"}</span></summary>{issue.description&&<p>{issue.description}</p>}{issue.articles.length?<ul className="public-article-list">{issue.articles.map(article=><li key={article.slug}><Link href={article.url}>{article.title}</Link>{article.demo&&<DemoBadge/>}</li>)}</ul>:<p className="muted-copy">No published articles are listed in this issue.</p>}</details>})}</div>
  </details>)}
  {error&&<PublicLoadError message={error} retry={reload}/>} 
 </PublicPageLayout>;
}
