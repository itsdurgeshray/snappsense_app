import { createContext, useContext } from "react";
import { defaultContent } from "./defaults";
import type { Content } from "./types";

export const ContentContext = createContext<Content>(defaultContent);

export function useContent(): Content {
  return useContext(ContentContext);
}
