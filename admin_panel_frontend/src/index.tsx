import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

// Получаем корневой элемент из index.html
const rootElement = document.getElementById('root');

if (rootElement) {
  ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
} else {
  console.error("Не найден корневой элемент #root в HTML.");
}