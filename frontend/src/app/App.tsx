import React from 'react';
import { BrowserRouter } from 'react-router-dom';
import { AppRouter } from './router';
import { AuthProvider } from './AuthContext';
import { ProjectProvider } from './ProjectContext';
import { ToastProvider } from './ToastContext';

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ProjectProvider>
          <ToastProvider>
            <AppRouter />
          </ToastProvider>
        </ProjectProvider>
      </AuthProvider>
    </BrowserRouter>
  );
};

export default App;
