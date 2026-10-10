import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { accountProfile, isAdmin, logout } from "./auth";
import { DocumentsPage } from "./features/documents/DocumentsPage";
import { ReviewPage } from "./features/documents/ReviewPage";
import { UploadPage } from "./features/documents/UploadPage";
import { HomePage } from "./features/dashboard/HomePage";
import { ProjectsPage } from "./features/projects/ProjectsPage";
import { ProjectManagerItemsPage } from "./features/projects/ProjectManagerItemsPage";
import { ItemEvaluationPage } from "./features/evaluation/ItemEvaluationPage";
import { ItemsEvaluationPage } from "./features/evaluation/ItemsEvaluationPage";
import { CategoryItemsPage } from "./features/category-items/CategoryItemsPage";
import { AnalyticsPage } from "./features/analytics/AnalyticsPage";
import { Button } from "./components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "./components/ui/avatar";
import { Popover, PopoverContent, PopoverTrigger } from "./components/ui/popover";
import { NavigationMenu, NavigationMenuItem, NavigationMenuLink, NavigationMenuList } from "./components/ui/navigation-menu";
import { LogOut } from "lucide-react";

const navigationItems = [
  { to: "/", label: "Inicio", end: true },
  { to: "/projects", label: "Proyectos" },
  { to: "/items/categories", label: "Ítems por categoría" },
  { to: "/items/evaluation", label: "Evaluación" },
  { to: "/documents/upload", label: "Cargar PDFs" },
  { to: "/documents", label: "Documentos", end: true },
  { to: "/analytics", label: "Analítica" },
] as const;

export function App() {
  const { pathname } = useLocation();
  const account = accountProfile();
  if (!isAdmin()) {
    return <main className="centered"><h1>Acceso restringido</h1><p>Tu cuenta no tiene el rol de administrador de Ingevec.</p><Button onClick={() => void logout()}>Cerrar sesión</Button></main>;
  }

  return (
    <main>
      <header className="app-header">
        <div><img src="/ingevec_logo.png" alt="Ingevec" className="mb-2 h-12 w-auto object-contain object-left" /><h1 className="font-bold">Gestión de filtraciones</h1></div>
        <Popover>
          <PopoverTrigger aria-label={`Cuenta de ${account.name}`} className="rounded-full outline-none transition-shadow hover:shadow-md focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
            <Avatar size="lg" className="cursor-pointer">
              {account.picture && <AvatarImage src={account.picture} alt={`Foto de ${account.name}`} />}
              <AvatarFallback>{account.initials}</AvatarFallback>
            </Avatar>
          </PopoverTrigger>
          <PopoverContent align="end" sideOffset={8} className="w-52 gap-0 overflow-hidden rounded-2xl border border-border bg-card p-0 text-foreground shadow-lg">
            <div className="px-4 py-3 text-xs font-semibold text-muted-foreground">{account.name}</div>
            <div className="h-px w-full bg-border" />
            <Button variant="ghost" size="sm" onClick={() => void logout()} className="h-8 min-h-8 w-full justify-center gap-1.5 px-4 text-xs font-medium text-foreground hover:bg-accent focus-visible:bg-accent [&_svg]:size-3.5">
              Cerrar sesión <LogOut aria-hidden="true" className="size-3.5" />
            </Button>
          </PopoverContent>
        </Popover>
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
      <Routes><Route path="/" element={<HomePage />} /><Route path="/analytics" element={<AnalyticsPage />} /><Route path="/projects" element={<ProjectsPage />} /><Route path="/project-managers/:projectManagerId/items" element={<ProjectManagerItemsPage />} /><Route path="/items/evaluation" element={<ItemsEvaluationPage />} /><Route path="/items/categories" element={<CategoryItemsPage />} /><Route path="/items/:publicId/evaluation" element={<ItemEvaluationPage />} /><Route path="/documents/upload" element={<UploadPage />} /><Route path="/documents" element={<DocumentsPage />} /><Route path="/documents/:publicId/review" element={<ReviewPage />} /><Route path="*" element={<Navigate to="/" replace />} /></Routes>
    </main>
  );
}
