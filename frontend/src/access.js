import { createContext, useContext } from 'react';

// canControl: this visitor may change things (start/stop the bot, open/close trades, ...)
export const AccessContext = createContext({ canControl: true });

export const useAccess = () => useContext(AccessContext);
