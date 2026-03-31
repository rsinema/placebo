import { BrowserRouter, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import MetricDetail from "./pages/MetricDetail";
import Experiments from "./pages/Experiments";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/metrics/:id" element={<MetricDetail />} />
          <Route path="/experiments" element={<Experiments />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
