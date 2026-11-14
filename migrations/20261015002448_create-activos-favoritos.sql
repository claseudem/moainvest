-- Activos de preferencia de cada usuario (se muestran en el sidebar de /app/).
CREATE TABLE public.activos_favoritos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  ticker TEXT NOT NULL CHECK (char_length(ticker) BETWEEN 1 AND 20),
  nombre TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, ticker)
);

CREATE INDEX activos_favoritos_user_idx ON public.activos_favoritos (user_id, created_at);

ALTER TABLE public.activos_favoritos ENABLE ROW LEVEL SECURITY;

CREATE POLICY "dueño lee sus favoritos" ON public.activos_favoritos
  FOR SELECT TO authenticated USING (user_id = (SELECT auth.uid()));

CREATE POLICY "dueño agrega favoritos" ON public.activos_favoritos
  FOR INSERT TO authenticated WITH CHECK (user_id = (SELECT auth.uid()));

CREATE POLICY "dueño borra sus favoritos" ON public.activos_favoritos
  FOR DELETE TO authenticated USING (user_id = (SELECT auth.uid()));

-- Sin acceso anónimo ni UPDATE: un favorito solo se agrega o se quita.
REVOKE ALL ON public.activos_favoritos FROM anon;
REVOKE UPDATE ON public.activos_favoritos FROM authenticated;
