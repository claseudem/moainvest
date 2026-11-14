/* Sección PERSONAS: botón "Invitar personas".
 *
 * Copia el enlace de registro (cuentas.registro) al portapapeles. Si el
 * navegador no permite copiar, deja seleccionado el campo para copiarlo a mano.
 * Sin JavaScript el enlace sigue visible en el campo de solo lectura.
 */
(() => {
  const button = document.querySelector("[data-copy-invite]");
  const input = document.getElementById("invite-link");
  const status = document.querySelector("[data-copy-status]");
  if (!button || !input) return;

  const say = (message) => {
    if (status) status.textContent = message;
  };

  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(input.value);
      say("Enlace copiado. Compártelo para invitar a más personas.");
    } catch {
      input.focus();
      input.select();
      say("Selecciona el enlace y cópialo con Ctrl+C.");
    }
  });
})();
