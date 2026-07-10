import "@douyinfe/semi-ui/react19-adapter";
import { LocaleProvider } from "@douyinfe/semi-ui";
import enUS from "@douyinfe/semi-ui/lib/es/locale/source/en_US";
import React from "react";
import ReactDOM from "react-dom/client";
import "@douyinfe/semi-ui/lib/es/_base/base.css";
import { App } from "./app/App";
import "./app/styles.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <LocaleProvider locale={enUS}>
      <App />
    </LocaleProvider>
  </React.StrictMode>,
);
