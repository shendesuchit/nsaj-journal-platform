import SearchResults from "./search-results";

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string | string[]; discipline?: string }>;
}) {
  const params = await searchParams;
  const queryValue = Array.isArray(params.q) ? params.q[0] : params.q;
  return <SearchResults key={`${queryValue ?? ""}:${params.discipline ?? ""}`} initialDiscipline={params.discipline ?? ""} initialQuery={queryValue ?? ""} />;
}
