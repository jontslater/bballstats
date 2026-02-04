import { createContext, useContext, useState, ReactNode } from 'react';

type Sport = 'NBA' | 'NFL';

interface SportContextType {
  sport: Sport;
  setSport: (sport: Sport) => void;
}

const SportContext = createContext<SportContextType | undefined>(undefined);

export function SportProvider({ children }: { children: ReactNode }) {
  const [sport, setSport] = useState<Sport>('NBA');

  return (
    <SportContext.Provider value={{ sport, setSport }}>
      {children}
    </SportContext.Provider>
  );
}

export function useSport() {
  const context = useContext(SportContext);
  if (context === undefined) {
    throw new Error('useSport must be used within a SportProvider');
  }
  return context;
}

