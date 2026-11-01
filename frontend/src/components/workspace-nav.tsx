"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { JournalIcon } from "@/components/journal-art";

const workspaces = [
  {href:"/admin/overview",label:"Journal control",icon:"layers",roles:["site_admin"]},
  {href:"/author/resources",label:"Preparation files",icon:"download",roles:["author"]},
  { href: "/author", label: "My manuscripts", icon: "file", roles: ["author"] },
  { href: "/reviewer", label: "Review assignments", icon: "check", roles: ["reviewer"] },
  { href: "/editorial", label: "Editorial cases", icon: "book", roles: ["editor_in_chief", "managing_editor", "associate_editor"] },
  { href: "/admin/publication", label: "Publication", icon: "book", roles: ["site_admin", "editor_in_chief", "managing_editor", "associate_editor"] },
  { href: "/admin/content", label: "Journal administration", icon: "technology", roles: ["site_admin", "editor_in_chief", "managing_editor", "associate_editor"] },
];

export function WorkspaceNav() {
  const pathname = usePathname();
  const privatePage = /^\/(author|reviewer|editorial|admin)(\/|$)/.test(pathname);
  const [roles, setRoles] = useState<string[]>([]);
  useEffect(() => {
    let active = true;
    if (privatePage) void api<{ roles?: string[] }>("/auth/me").then(user => { if (active) setRoles(user.roles ?? []); }).catch(() => { if (active) setRoles([]); });
    return () => { active = false; };
  }, [privatePage, pathname]);
  if (!privatePage || !roles.length) return null;
  // Navigation is a convenience only. Each endpoint retains its own authorization.
  const links = workspaces.filter(item => item.roles.some(role => roles.includes(role)) && !(roles.includes("site_admin") && item.href === "/editorial"));
  return <nav className="workspace-navigation" aria-label="Your workspaces"><div><span className="workspace-navigation__label">Workspace</span>{links.map(item => <Link key={item.href} href={item.href} aria-current={pathname === item.href || (item.href !== "/author" && pathname.startsWith(`${item.href}/`)) ? "page" : undefined}><JournalIcon name={item.icon} size={14} />{item.label}</Link>)}</div></nav>;
}
