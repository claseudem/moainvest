-- Votos de sentimiento de COMUNIDAD: cada usuario vota si un activo "sube" o "baja".
CREATE TABLE IF NOT EXISTS public.votos_activos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  ticker TEXT NOT NULL CHECK (char_length(ticker) BETWEEN 1 AND 20),
  voto TEXT NOT NULL CHECK (voto IN ('sube', 'baja')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, ticker)
);

CREATE INDEX IF NOT EXISTS votos_activos_ticker_idx ON public.votos_activos (ticker);

ALTER TABLE public.votos_activos ENABLE ROW LEVEL SECURITY;

-- El conteo es público para quien inició sesión; cada voto solo lo cambia su dueño.
CREATE POLICY "usuarios leen los votos" ON public.votos_activos
  FOR SELECT TO authenticated USING (true);

CREATE POLICY "dueño vota" ON public.votos_activos
  FOR INSERT TO authenticated WITH CHECK (user_id = (SELECT auth.uid()));

CREATE POLICY "dueño retira su voto" ON public.votos_activos
  FOR DELETE TO authenticated USING (user_id = (SELECT auth.uid()));

-- Cambiar un voto = borrarlo y crear otro: sin UPDATE ni acceso anónimo.
REVOKE ALL ON public.votos_activos FROM anon;
REVOKE UPDATE ON public.votos_activos FROM authenticated;
