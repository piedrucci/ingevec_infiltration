import { NavLink, Navigate, Route, Routes } from "react-router-dom";

import { isAdmin, logout } from "./auth";
import { DocumentsPage } from "./features/documents/DocumentsPage";
import { ReviewPage } from "./features/documents/ReviewPage";
import { UploadPage } from "./features/documents/UploadPage";
import { HomePage } from "./features/dashboard/HomePage";
import { ProjectsPage } from "./features/projects/ProjectsPage";
import { ProjectManagerItemsPage } from "./features/projects/ProjectManagerItemsPage";
import { ItemEvaluationPage } from "./features/evaluation/ItemEvaluationPage";
import { ItemsEvaluationPage } from "./features/evaluation/ItemsEvaluationPage";
import { Button } from "./components/ui/button";

export function App() {
  if (!isAdmin()) {
    return <main className="centered"><h1>Acceso restringido</h1><p>Tu cuenta no tiene el rol de administrador de Ingevec.</p><Button onClick={() => void logout()}>Cerrar sesión</Button></main>;
  }

  return (
    <main>
      <header className="app-header">
        <div><p className="eyebrow">INGEVEC · POSTVENTA</p><h1>Gestión de filtraciones</h1></div>
        <Button variant="secondary" onClick={() => void logout()}>Cerrar sesión</Button>
      </header>
      <nav className="app-nav"><NavLink to="/">Inicio</NavLink><NavLink to="/projects">Proyectos</NavLink><NavLink to="/items/evaluation">Evaluación</NavLink><NavLink to="/documents/upload">Cargar PDFs</NavLink><NavLink to="/documents" end>Documentos</NavLink></nav>
      <Routes><Route path="/" element={<HomePage />} /><Route path="/projects" element={<ProjectsPage />} /><Route path="/project-managers/:projectManagerId/items" element={<ProjectManagerItemsPage />} /><Route path="/items/evaluation" element={<ItemsEvaluationPage />} /><Route path="/items/:publicId/evaluation" element={<ItemEvaluationPage />} /><Route path="/documents/upload" element={<UploadPage />} /><Route path="/documents" element={<DocumentsPage />} /><Route path="/documents/:publicId/review" element={<ReviewPage />} /><Route path="*" element={<Navigate to="/" replace />} /></Routes>
    </main>
  );
}
