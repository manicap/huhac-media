import { createContext, type ReactNode, useContext } from "react";

import type { StudioDataSource } from "./contracts";

const StudioDataContext = createContext<StudioDataSource | null>(null);

export function StudioDataProvider({
  children,
  dataSource,
}: {
  children: ReactNode;
  dataSource: StudioDataSource;
}) {
  return (
    <StudioDataContext.Provider value={dataSource}>
      {children}
    </StudioDataContext.Provider>
  );
}

export function useStudioData(): StudioDataSource {
  const dataSource = useContext(StudioDataContext);
  if (!dataSource) {
    throw new Error("StudioDataProvider is missing");
  }
  return dataSource;
}
