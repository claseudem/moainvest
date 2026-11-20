-- COMUNIDAD: perfil público, notas por activo y relaciones (seguir / conectar).

-- Perfil de comunidad (uno por usuario). Solo se muestra a otros si visible = true.
CREATE TABLE IF NOT EXISTS public.perfiles_comunidad (
  user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  nombre TEXT CHECK (char_length(nombre) <= 60),
  profesion TEXT CHECK (char_length(profesion) <= 60),
  bio TEXT CHECK (char_length(bio) <= 280),
  perfil TEXT CHECK (char_length(perfil) <= 40),
  -- Foto reducida en el navegador (data:image/jpeg;base64,...) o "iniciales:<color>".
  avatar TEXT CHECK (char_length(avatar) <= 80000),
  visible BOOLEAN NOT NULL DEFAULT false,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.perfiles_comunidad ENABLE ROW LEVEL SECURITY;

CREATE POLICY "se leen perfiles visibles y el propio" ON public.perfiles_comunidad
  FOR SELECT TO authenticated USING (visible OR user_id = (SELECT auth.uid()));
CREATE POLICY "dueño crea su perfil" ON public.perfiles_comunidad
  FOR INSERT TO authenticated WITH CHECK (user_id = (SELECT auth.uid()));
CREATE POLICY "dueño edita su perfil" ON public.perfiles_comunidad
  FOR UPDATE TO authenticated USING (user_id = (SELECT auth.uid())) WITH CHECK (user_id = (SELECT auth.uid()));
CREATE POLICY "dueño borra su perfil" ON public.perfiles_comunidad
  FOR DELETE TO authenticated USING (user_id = (SELECT auth.uid()));
REVOKE ALL ON public.perfiles_comunidad FROM anon;

-- Nota corta o reacción rápida de un usuario sobre un activo: su tesis (una por activo).
CREATE TABLE IF NOT EXISTS public.notas_activos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  ticker TEXT NOT NULL CHECK (char_length(ticker) BETWEEN 1 AND 20),
  etiqueta TEXT CHECK (char_length(etiqueta) <= 40),
  texto TEXT CHECK (char_length(texto) <= 140),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, ticker),
  CHECK (etiqueta IS NOT NULL OR texto IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS notas_activos_ticker_idx ON public.notas_activos (ticker, created_at DESC);

ALTER TABLE public.notas_activos ENABLE ROW LEVEL SECURITY;

CREATE POLICY "usuarios leen las notas" ON public.notas_activos
  FOR SELECT TO authenticated USING (true);
CREATE POLICY "dueño escribe su nota" ON public.notas_activos
  FOR INSERT TO authenticated WITH CHECK (user_id = (SELECT auth.uid()));
CREATE POLICY "dueño borra su nota" ON public.notas_activos
  FOR DELETE TO authenticated USING (user_id = (SELECT auth.uid()));
REVOKE ALL ON public.notas_activos FROM anon;
REVOKE UPDATE ON public.notas_activos FROM authenticated;

-- Seguir a un perfil público o pedir conexión (la conexión es mutua cuando ambos la piden).
CREATE TABLE IF NOT EXISTS public.relaciones_comunidad (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  objetivo_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  tipo TEXT NOT NULL CHECK (tipo IN ('seguir', 'conectar')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, objetivo_id, tipo),
  CHECK (user_id <> objetivo_id)
);

ALTER TABLE public.relaciones_comunidad ENABLE ROW LEVEL SECURITY;

CREATE POLICY "se leen las relaciones propias" ON public.relaciones_comunidad
  FOR SELECT TO authenticated USING (user_id = (SELECT auth.uid()) OR objetivo_id = (SELECT auth.uid()));
CREATE POLICY "dueño crea relaciones" ON public.relaciones_comunidad
  FOR INSERT TO authenticated WITH CHECK (user_id = (SELECT auth.uid()));
CREATE POLICY "dueño borra relaciones" ON public.relaciones_comunidad
  FOR DELETE TO authenticated USING (user_id = (SELECT auth.uid()));
REVOKE ALL ON public.relaciones_comunidad FROM anon;
REVOKE UPDATE ON public.relaciones_comunidad FROM authenticated;
