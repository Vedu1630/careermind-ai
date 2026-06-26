import { create } from "zustand";
import { onAuthChange, logOut } from "../lib/firebase";

const useAuthStore = create((set) => ({
  user:    null,
  loading: true,
  error:   null,

  setError:   (error) => set({ error }),
  clearError: ()      => set({ error: null }),

  signOut: async () => {
    await logOut();
    set({ user: null });
  },

  initAuth: () => {
    return onAuthChange((firebaseUser) => {
      if (firebaseUser) {
        set({
          user: {
            uid:      firebaseUser.uid,
            name:     firebaseUser.displayName || "User",
            email:    firebaseUser.email,
            photo:    firebaseUser.photoURL || null,
            provider: firebaseUser.providerData[0]?.providerId || "email",
          },
          loading: false,
          error: null,
        });
      } else {
        set({ user: null, loading: false });
      }
    });
  },
}));

export default useAuthStore;
