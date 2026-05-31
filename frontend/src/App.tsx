import { useEffect, useState } from "react";
import { Layout } from "./components/Layout";
import { CardDetailPage } from "./pages/CardDetailPage";
import { CollectionPage } from "./pages/CollectionPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DebugPage } from "./pages/DebugPage";
import { SettingsPage } from "./pages/SettingsPage";

export type Page = "dashboard" | "collection" | "detail" | "add" | "settings" | "debug";

function parseHash(): { page: Page; ownedCardId: number | null } {
  const hash = window.location.hash.replace(/^#\/?/, "");
  const [page, id] = hash.split("/");
  if (page === "collection") return { page: "collection", ownedCardId: null };
  if (page === "add") return { page: "add", ownedCardId: null };
  if (page === "settings") return { page: "settings", ownedCardId: null };
  if (page === "debug") return { page: "debug", ownedCardId: null };
  if (page === "owned-cards" && id) return { page: "detail", ownedCardId: Number(id) };
  return { page: "dashboard", ownedCardId: null };
}

export default function App() {
  const initial = parseHash();
  const [page, setPage] = useState<Page>(initial.page);
  const [ownedCardId, setOwnedCardId] = useState<number | null>(initial.ownedCardId);
  const [debugMode, setDebugMode] = useState(() => window.localStorage.getItem("cardgrader-debug-mode") === "true");

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

  const toggleDebugMode = () => {
    setDebugMode((current) => {
      const next = !current;
      window.localStorage.setItem("cardgrader-debug-mode", String(next));
      return next;
    });
  };

  const openOwnedCard = (id: number) => {
    setPage("detail");
    setOwnedCardId(id);
    window.location.hash = `#/owned-cards/${id}`;
  };

  return (
    <Layout page={page} debugMode={debugMode} onNavigate={navigate} onToggleDebugMode={toggleDebugMode}>
      {page === "dashboard" && <DashboardPage />}
      {page === "collection" && <CollectionPage mode="browse" onOpenOwnedCard={openOwnedCard} />}
      {page === "add" && <CollectionPage mode="add" onOpenOwnedCard={openOwnedCard} />}
      {page === "detail" && ownedCardId !== null && <CardDetailPage ownedCardId={ownedCardId} debugMode={debugMode} onDeleted={() => navigate("collection")} />}
      {page === "settings" && <SettingsPage debugMode={debugMode} onToggleDebugMode={toggleDebugMode} />}
      {page === "debug" && <DebugPage />}
    </Layout>
  );
}
