import { NavLink, Navigate, Route, Routes } from "react-router-dom";

import { isAdmin, logout } from "./auth";
import { DocumentsPage } from "./features/documents/DocumentsPage";
import { ReviewPage } from "./features/documents/ReviewPage";
import { UploadPage } from "./features/documents/UploadPage";
import { HomePage } from "./features/dashboard/HomePage";
import { ProjectsPage } from "./features/projects/ProjectsPage";

export function App() {
  if (!isAdmin()) {
    return <main className="centered"><h1>Acceso restringido</h1><p>Tu cuenta no tiene el rol de administrador de Ingevec.</p><button onClick={() => void logout()}>Cerrar sesión</button></main>;
  }

  return (
    <main>
      <header className="app-header">
        <div><p className="eyebrow">INGEVEC · POSTVENTA</p><h1>Gestión de filtraciones</h1></div>
        <button className="secondary" onClick={() => void logout()}>Cerrar sesión</button>
      </header>
      <nav className="app-nav"><NavLink to="/">Inicio</NavLink><NavLink to="/projects">Proyectos</NavLink><NavLink to="/documents/upload">Cargar PDFs</NavLink><NavLink to="/documents">Documentos</NavLink></nav>
      <Routes><Route path="/" element={<HomePage />} /><Route path="/projects" element={<ProjectsPage />} /><Route path="/documents/upload" element={<UploadPage />} /><Route path="/documents" element={<DocumentsPage />} /><Route path="/documents/:publicId/review" element={<ReviewPage />} /><Route path="*" element={<Navigate to="/" replace />} /></Routes>
    </main>
  );
}
