-- "¿Qué piensas tú?" (/app/que-piensas-tu/): ¿el activo sube o baja esta semana?
-- Un voto por usuario, activo y ronda semanal (semana ISO en UTC, p. ej. 2026-W46).
-- El usuario puede cambiar su voto mientras la ronda siga abierta.
CREATE TABLE public.votos_activos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  ticker TEXT NOT NULL CHECK (char_length(ticker) BETWEEN 1 AND 20),
  voto TEXT NOT NULL CHECK (voto IN ('up', 'down')),
  ronda TEXT NOT NULL CHECK (ronda ~ '^[0-9]{4}-W[0-9]{2}$'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, ticker, ronda)
);

-- Los recuentos se piden por ronda y ticker.
CREATE INDEX votos_activos_ronda_ticker_idx ON public.votos_activos (ronda, ticker);

ALTER TABLE public.votos_activos ENABLE ROW LEVEL SECURITY;

-- Con su JWT, cada usuario solo ve, crea y cambia sus propios votos. Los
-- totales de la comunidad los calcula el servidor con la API key y solo
-- publica recuentos.
CREATE POLICY "dueño lee sus votos" ON public.votos_activos
  FOR SELECT TO authenticated USING (user_id = (SELECT auth.uid()));

CREATE POLICY "dueño vota" ON public.votos_activos
  FOR INSERT TO authenticated WITH CHECK (user_id = (SELECT auth.uid()));

CREATE POLICY "dueño cambia su voto" ON public.votos_activos
  FOR UPDATE TO authenticated USING (user_id = (SELECT auth.uid())) WITH CHECK (user_id = (SELECT auth.uid()));

-- Solo se puede cambiar el sentido del voto (no el activo ni la ronda) y nunca borrarlo.
REVOKE ALL ON public.votos_activos FROM anon;
REVOKE UPDATE, DELETE ON public.votos_activos FROM authenticated;
GRANT UPDATE (voto, updated_at) ON public.votos_activos TO authenticated;
