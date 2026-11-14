-- Alertas de movimientos bruscos (campana de /app/ y paso 01 de Informes).

-- Preferencias de cada usuario: umbral (±3/5/10 %) y watchlists silenciadas.
CREATE TABLE public.alertas_preferencias (
  user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  umbral SMALLINT NOT NULL DEFAULT 5 CHECK (umbral IN (3, 5, 10)),
  silenciadas TEXT[] NOT NULL DEFAULT '{}',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Cada aviso enviado, con su titular de contexto (si lo había).
-- ``sesion`` = cierre anterior del activo: identifica la sesión de mercado.
-- La restricción UNIQUE es el anti-ruido definitivo: un aviso por activo,
-- sesión, dirección y nivel (1×, 2× o 3× el umbral), aunque varios procesos
-- evalúen a la vez.
CREATE TABLE public.alertas (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  ticker TEXT NOT NULL CHECK (char_length(ticker) BETWEEN 1 AND 20),
  nombre TEXT,
  watchlists TEXT[] NOT NULL DEFAULT '{}',
  variacion NUMERIC(10, 4) NOT NULL,
  precio DOUBLE PRECISION,
  moneda TEXT,
  direccion TEXT NOT NULL CHECK (direccion IN ('up', 'down')),
  nivel SMALLINT NOT NULL CHECK (nivel BETWEEN 1 AND 3),
  umbral SMALLINT NOT NULL CHECK (umbral IN (3, 5, 10)),
  sesion TEXT NOT NULL,
  noticia_titulo TEXT,
  noticia_fuente TEXT,
  noticia_url TEXT,
  noticia_fecha TIMESTAMPTZ,
  leida BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, ticker, sesion, direccion, nivel)
);

CREATE INDEX alertas_user_created_idx ON public.alertas (user_id, created_at DESC);
CREATE INDEX alertas_user_unread_idx ON public.alertas (user_id) WHERE NOT leida;

ALTER TABLE public.alertas_preferencias ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.alertas ENABLE ROW LEVEL SECURITY;

CREATE POLICY "dueño lee sus preferencias" ON public.alertas_preferencias
  FOR SELECT TO authenticated USING (user_id = (SELECT auth.uid()));
CREATE POLICY "dueño crea sus preferencias" ON public.alertas_preferencias
  FOR INSERT TO authenticated WITH CHECK (user_id = (SELECT auth.uid()));
CREATE POLICY "dueño cambia sus preferencias" ON public.alertas_preferencias
  FOR UPDATE TO authenticated USING (user_id = (SELECT auth.uid())) WITH CHECK (user_id = (SELECT auth.uid()));

-- Las alertas las crea el servidor; el usuario solo las lee y las marca como leídas.
CREATE POLICY "dueño lee sus alertas" ON public.alertas
  FOR SELECT TO authenticated USING (user_id = (SELECT auth.uid()));
CREATE POLICY "dueño marca sus alertas" ON public.alertas
  FOR UPDATE TO authenticated USING (user_id = (SELECT auth.uid())) WITH CHECK (user_id = (SELECT auth.uid()));

REVOKE ALL ON public.alertas_preferencias FROM anon;
REVOKE ALL ON public.alertas FROM anon;
REVOKE INSERT, DELETE ON public.alertas FROM authenticated;
REVOKE UPDATE ON public.alertas FROM authenticated;
GRANT UPDATE (leida) ON public.alertas TO authenticated;
