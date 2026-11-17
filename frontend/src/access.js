import { createContext, useContext } from 'react';

// The logged-in user. canControl: may trade their own account (every logged-in user).
// isAdmin: may manage users and the shared bot (scanner, retraining, forced cycles).
export const AccessContext = createContext({ user: null, isAdmin: false, canControl: true });

export const useAccess = () => useContext(AccessContext);
