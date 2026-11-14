-- Suscripción a alertas de noticias (/app/noticias/): una fila por usuario.
--   via_app    → titulares nuevos en la pestaña "Noticias" de la campana
--   via_email  → resumen por correo (``flask noticias-digest``, vía Resend)
--   alcance    → 'todos' (catálogo de la plataforma) o 'favoritos' (Mis activos)
CREATE TABLE public.suscripciones_noticias (
  user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  activa BOOLEAN NOT NULL DEFAULT FALSE,
  via_app BOOLEAN NOT NULL DEFAULT TRUE,
  via_email BOOLEAN NOT NULL DEFAULT FALSE,
  email TEXT CHECK (email IS NULL OR (char_length(email) <= 254 AND email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$')),
  alcance TEXT NOT NULL DEFAULT 'favoritos' CHECK (alcance IN ('todos', 'favoritos')),
  ultimo_envio TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  -- Sin canal no hay suscripción activa; el correo exige dirección.
  CHECK (NOT activa OR via_app OR via_email),
  CHECK (NOT via_email OR email IS NOT NULL)
);

-- El resumen por correo recorre solo las suscripciones activas con correo.
CREATE INDEX suscripciones_noticias_email_idx ON public.suscripciones_noticias (user_id) WHERE activa AND via_email;

ALTER TABLE public.suscripciones_noticias ENABLE ROW LEVEL SECURITY;

CREATE POLICY "dueño lee su suscripción" ON public.suscripciones_noticias
  FOR SELECT TO authenticated USING (user_id = (SELECT auth.uid()));
CREATE POLICY "dueño crea su suscripción" ON public.suscripciones_noticias
  FOR INSERT TO authenticated WITH CHECK (user_id = (SELECT auth.uid()));
CREATE POLICY "dueño cambia su suscripción" ON public.suscripciones_noticias
  FOR UPDATE TO authenticated USING (user_id = (SELECT auth.uid())) WITH CHECK (user_id = (SELECT auth.uid()));

-- ``ultimo_envio`` solo lo escribe el servidor (comando de resumen).
REVOKE ALL ON public.suscripciones_noticias FROM anon;
REVOKE UPDATE ON public.suscripciones_noticias FROM authenticated;
GRANT UPDATE (activa, via_app, via_email, email, alcance, updated_at) ON public.suscripciones_noticias TO authenticated;
