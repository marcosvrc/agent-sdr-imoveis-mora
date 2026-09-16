import { create } from "zustand";
import { persist } from "zustand/middleware";

// Favoritar é só conveniência do visitante (comparar depois) — fica no navegador dele, não no servidor.
type EstadoFavoritos = { ids: string[]; alternar: (id: string) => void; tem: (id: string) => boolean };

export const useFavoritos = create<EstadoFavoritos>()(
  persist(
    (set, get) => ({
      ids: [],
      alternar: (id) => set((s) => ({ ids: s.ids.includes(id) ? s.ids.filter((x) => x !== id) : [...s.ids, id] })),
      tem: (id) => get().ids.includes(id),
    }),
    { name: "sdr_favoritos" },
  ),
);
