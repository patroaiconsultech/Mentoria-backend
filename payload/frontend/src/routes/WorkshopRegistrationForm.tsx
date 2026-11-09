import React, { FormEvent, useState } from "react";
import { publicEnv } from "../config/runtime";
import "./WorkshopRegistrationForm.css";

type RegistrationOutcome = "idle" | "sending" | "done" | "error";

export function securePrivacyUrl(raw: string | undefined): string | null {
  try {
    const url = new URL((raw || "").trim());
    if (url.protocol !== "https:" || !url.hostname || url.username || url.password) return null;
    return url.toString();
  } catch {
    return null;
  }
}

export function registrationFormConfig() {
  const privacyUrl = securePrivacyUrl(import.meta.env.VITE_MENTORIA_PRIVACY_URL);
  const version = (import.meta.env.VITE_MENTORIA_PRIVACY_VERSION || "").trim();
  const enabled = import.meta.env.VITE_MENTORIA_REGISTRATION_ENABLED === "true";
  return { enabled: enabled && Boolean(privacyUrl) && /^[a-zA-Z0-9._-]{1,40}$/.test(version),
    privacyUrl, version };
}

const ERRORS: Record<string, string> = {
  MENTORIA_WORKSHOP_DISABLED: "As inscrições ainda não foram abertas.",
  MENTORIA_WORKSHOP_CONFIGURATION_MISSING: "As inscrições não estão disponíveis neste momento.",
  MENTORIA_PRIVACY_ACKNOWLEDGEMENT_REQUIRED: "Confira a política de privacidade e confirme sua leitura.",
  MENTORIA_RATE_LIMITED: "Foram realizadas várias tentativas. Tente novamente mais tarde.",
  MENTORIA_REGISTRATION_UNAVAILABLE: "Não foi possível registrar sua inscrição. Tente novamente.",
  MENTORIA_RATE_LIMIT_UNAVAILABLE: "Inscrições temporariamente indisponíveis.",
  MENTORIA_ORIGIN_INVALID: "Este endereço não está autorizado para inscrições.",
};

export default function WorkshopRegistrationForm() {
  const config = registrationFormConfig();
  const [status, setStatus] = useState<RegistrationOutcome>("idle");
  const [message, setMessage] = useState("");
  const [accepted, setAccepted] = useState(false);
  const [marketing, setMarketing] = useState(false);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [company, setCompany] = useState("");
  const [website, setWebsite] = useState("");

  if (!config.enabled || !config.privacyUrl) return null;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!accepted || status === "sending") return;
    setStatus("sending");
    setMessage("");
    const base = publicEnv("VITE_API_BASE_URL").replace(/\/$/, "");
    const url = `${base}/api/v2/public/mentoria/workshop-registrations`;
    try {
      const response = await fetch(url, {
        method: "POST",
        credentials: "omit",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          full_name: fullName.trim(),
          email: email.trim(),
          company_name: company.trim() || null,
          privacy_notice_version: config.version,
          privacy_accepted: accepted,
          marketing_opt_in: marketing,
          website,
        }),
      });
      if (response.status !== 202) {
        let code = "";
        try {
          const body = await response.json() as { detail?: string };
          code = typeof body.detail === "string" ? body.detail : "";
        } catch {
          // Do not expose arbitrary HTTP bodies or sensitive server internals.
        }
        throw new Error(ERRORS[code] || (response.status === 422
          ? "Confira os dados preenchidos."
          : "Não foi possível completar a inscrição."));
      }
      setStatus("done");
      setMessage("Recebemos sua solicitação. Confira os canais oficiais para novidades do workshop.");
      setFullName("");
      setEmail("");
      setCompany("");
      setWebsite("");
      setAccepted(false);
      setMarketing(false);
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "Erro de conexão. Tente novamente.");
    }
  }

  return (
    <form className="dg-mentoria-form" onSubmit={submit} aria-label="Inscrição para o workshop">
      <h3>Quero participar do workshop</h3>
      <p>Cadastre seu interesse. Datas e demais detalhes serão divulgados pelos canais oficiais.</p>
      <label htmlFor="dg-ws-name">Nome completo</label>
      <input id="dg-ws-name" autoComplete="name" required minLength={2} maxLength={160}
        value={fullName} onChange={(event) => setFullName(event.target.value)}
        disabled={status === "sending" || status === "done"} />
      <label htmlFor="dg-ws-email">E-mail</label>
      <input id="dg-ws-email" type="email" autoComplete="email" required maxLength={320}
        value={email} onChange={(event) => setEmail(event.target.value)}
        disabled={status === "sending" || status === "done"} />
      <label htmlFor="dg-ws-company">Empresa (opcional)</label>
      <input id="dg-ws-company" autoComplete="organization" maxLength={160}
        value={company} onChange={(event) => setCompany(event.target.value)}
        disabled={status === "sending" || status === "done"} />
      <div className="dg-mentoria-form__honeypot" aria-hidden="true">
        <label htmlFor="dg-ws-website">Website</label>
        <input id="dg-ws-website" name="website" autoComplete="off" tabIndex={-1}
          value={website} onChange={(event) => setWebsite(event.target.value)} />
      </div>
      <label className="dg-mentoria-form__check">
        <input type="checkbox" required checked={accepted}
          onChange={(event) => setAccepted(event.target.checked)}
          disabled={status === "sending" || status === "done"} />
        <span>Li e compreendi a <a href={config.privacyUrl} target="_blank" rel="noopener noreferrer">
          Política de Privacidade</a> (versão {config.version}).</span>
      </label>
      <label className="dg-mentoria-form__check">
        <input type="checkbox" checked={marketing}
          onChange={(event) => setMarketing(event.target.checked)}
          disabled={status === "sending" || status === "done"} />
        <span>Também quero receber novidades e ofertas da mentoria por e-mail. (Opcional)</span>
      </label>
      {status !== "done" && (
        <button className="dg-mentoria__button dg-mentoria__button--primary"
          type="submit" disabled={status === "sending" || !accepted}>
          {status === "sending" ? "Enviando..." : "Registrar meu interesse"}
        </button>
      )}
      {message && <p className={`dg-mentoria-form__message dg-mentoria-form__message--${status}`}
        role={status === "error" ? "alert" : "status"}>{message}</p>}
      <small>Não há cobrança nesta etapa. Inscrição no workshop não equivale à matrícula na mentoria.</small>
    </form>
  );
}
