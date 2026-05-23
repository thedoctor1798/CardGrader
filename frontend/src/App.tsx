import { useEffect, useState } from "react";
import { EmptyState } from "./components/EmptyState";
import { Layout } from "./components/Layout";
import { CardDetailPage } from "./pages/CardDetailPage";
import { CollectionPage } from "./pages/CollectionPage";
import { DashboardPage } from "./pages/DashboardPage";

export type Page = "dashboard" | "collection" | "detail" | "settings";

function parseHash(): { page: Page; ownedCardId: number | null } {
  const hash = window.location.hash.replace(/^#\/?/, "");
  const [page, id] = hash.split("/");
  if (page === "collection") return { page: "collection", ownedCardId: null };
  if (page === "settings") return { page: "settings", ownedCardId: null };
  if (page === "owned-cards" && id) return { page: "detail", ownedCardId: Number(id) };
  return { page: "dashboard", ownedCardId: null };
}

export default function App() {
  const initial = parseHash();
  const [page, setPage] = useState<Page>(initial.page);
  const [ownedCardId, setOwnedCardId] = useState<number | null>(initial.ownedCardId);

  useEffect(() => {
    const onHashChange = () => {
      const next = parseHash();
      setPage(next.page);
      setOwnedCardId(next.ownedCardId);
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const navigate = (nextPage: Page) => {
    setPage(nextPage);
    if (nextPage !== "detail") setOwnedCardId(null);
    const hash = nextPage === "dashboard" ? "#/" : `#/${nextPage}`;
    window.location.hash = hash;
  };

  const openOwnedCard = (id: number) => {
    setPage("detail");
    setOwnedCardId(id);
    window.location.hash = `#/owned-cards/${id}`;
  };

  return (
    <Layout page={page} onNavigate={navigate}>
      {page === "dashboard" && <DashboardPage />}
      {page === "collection" && <CollectionPage onOpenOwnedCard={openOwnedCard} />}
      {page === "detail" && ownedCardId !== null && <CardDetailPage ownedCardId={ownedCardId} />}
      {page === "settings" && <EmptyState label="Beállítások placeholder. A lokális mód és API tiltások jelenleg fixek." />}
    </Layout>
  );
}
