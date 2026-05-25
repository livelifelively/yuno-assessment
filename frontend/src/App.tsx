import { Route, Routes } from "react-router-dom";

import { SplashPage } from "./routes/SplashPage";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<SplashPage />} />
      <Route path="*" element={<SplashPage />} />
    </Routes>
  );
}
