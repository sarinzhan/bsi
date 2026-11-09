import { Navigate, Outlet, Route, Routes } from 'react-router-dom';
import { CurrentUserProvider } from './auth';
import Sidebar from './components/Sidebar';
import ChatPage from './pages/ChatPage';
import HistoryPage from './pages/HistoryPage';
import ProjectPage from './pages/ProjectPage';
import RunningPage from './pages/RunningPage';
import ServerSettingsPage from './pages/ServerSettingsPage';
import ServersPage from './pages/ServersPage';
import SkillsPage from './pages/SkillsPage';
import UsersPage from './pages/UsersPage';

function Layout() {
  return (
    <div className="shell">
      <Sidebar />
      <div className="main">
        <Outlet />
      </div>
    </div>
  );
}

export default function App() {
  return (
    <CurrentUserProvider>
    <Routes>
      <Route path="/" element={<Navigate to="/superapp/chats/c-orders" replace />} />
      <Route path="/:systemId" element={<Layout />}>
        <Route index element={<Navigate to="chats/new" replace />} />
        <Route path="projects/:projectId" element={<ProjectPage />} />
        <Route path="chats/:chatId" element={<ChatPage />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="running" element={<RunningPage />} />
        <Route path="servers" element={<ServersPage />} />
        <Route path="servers/:serverName" element={<ServerSettingsPage />} />
        <Route path="skills" element={<SkillsPage />} />
        <Route path="users" element={<UsersPage />} />
        <Route path="*" element={<Navigate to="chats/new" replace />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </CurrentUserProvider>
  );
}
