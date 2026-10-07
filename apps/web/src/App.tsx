import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { isAdmin, logout } from "./auth";
import { DocumentsPage } from "./features/documents/DocumentsPage";
import { ReviewPage } from "./features/documents/ReviewPage";
import { UploadPage } from "./features/documents/UploadPage";
import { HomePage } from "./features/dashboard/HomePage";
import { ProjectsPage } from "./features/projects/ProjectsPage";
import { ProjectManagerItemsPage } from "./features/projects/ProjectManagerItemsPage";
import { ItemEvaluationPage } from "./features/evaluation/ItemEvaluationPage";
import { ItemsEvaluationPage } from "./features/evaluation/ItemsEvaluationPage";
import { CategoryItemsPage } from "./features/category-items/CategoryItemsPage";
import { Button } from "./components/ui/button";
import { NavigationMenu, NavigationMenuItem, NavigationMenuLink, NavigationMenuList } from "./components/ui/navigation-menu";

const navigationItems = [
  { to: "/", label: "Inicio", end: true },
  { to: "/projects", label: "Proyectos" },
  { to: "/items/categories", label: "Ítems por categoría" },
  { to: "/items/evaluation", label: "Evaluación" },
  { to: "/documents/upload", label: "Cargar PDFs" },
  { to: "/documents", label: "Documentos", end: true },
] as const;

export function App() {
  const { pathname } = useLocation();
  if (!isAdmin()) {
    return <main className="centered"><h1>Acceso restringido</h1><p>Tu cuenta no tiene el rol de administrador de Ingevec.</p><Button onClick={() => void logout()}>Cerrar sesión</Button></main>;
  }

  return (
    <main>
      <header className="app-header">
        <div><p className="eyebrow">INGEVEC · POSTVENTA</p><h1>Gestión de filtraciones</h1></div>
        <Button variant="secondary" onClick={() => void logout()}>Cerrar sesión</Button>
      </header>
      <NavigationMenu className="mb-6 overflow-x-auto pb-1">
        <NavigationMenuList>
          {navigationItems.map((item) => {
            const end = "end" in item && item.end;
            const { to, label } = item;
            const active = end ? pathname === to : pathname === to || pathname.startsWith(`${to}/`);
            return <NavigationMenuItem key={to}>
              <NavigationMenuLink active={active} aria-current={active ? "page" : undefined} render={<NavLink to={to} end={end} />}>{label}</NavigationMenuLink>
            </NavigationMenuItem>;
          })}
        </NavigationMenuList>
      </NavigationMenu>
      <Routes><Route path="/" element={<HomePage />} /><Route path="/projects" element={<ProjectsPage />} /><Route path="/project-managers/:projectManagerId/items" element={<ProjectManagerItemsPage />} /><Route path="/items/evaluation" element={<ItemsEvaluationPage />} /><Route path="/items/categories" element={<CategoryItemsPage />} /><Route path="/items/:publicId/evaluation" element={<ItemEvaluationPage />} /><Route path="/documents/upload" element={<UploadPage />} /><Route path="/documents" element={<DocumentsPage />} /><Route path="/documents/:publicId/review" element={<ReviewPage />} /><Route path="*" element={<Navigate to="/" replace />} /></Routes>
    </main>
  );
}
