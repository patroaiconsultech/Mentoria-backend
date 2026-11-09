import React, { FormEvent, useRef, useState } from "react";
import { publicEnv } from "../config/runtime";
import { securePrivacyUrl } from "./WorkshopRegistrationForm";
import "./MentoriaAssistant.css";

type ConversationItem = { id: number; author: "visitor" | "assistant"; text: string };
type ReplyPayload = { reply?: unknown; source?: unknown; catalog_version?: unknown };

const STARTERS = [
  "Como funciona a mentoria?",
  "Como identificar oportunidades de IA no meu negócio?",
  "Quando serão abertas as inscrições?",
];

const ERROR_MESSAGES: Record<string, string> = {
  MENTORIA_ASSISTANT_DISABLED: "O assistente está temporariamente indisponível.",
  MENTORIA_ASSISTANT_CONFIGURATION_MISSING: "A orientação por IA ainda não foi liberada.",
  MENTORIA_ASSISTANT_ACKNOWLEDGEMENT_REQUIRED: "Confirme a ciência do processamento por IA.",
  MENTORIA_ASSISTANT_UNAVAILABLE: "Não foi possível responder agora. Tente novamente mais tarde.",
  MENTORIA_RATE_LIMITED: "Você atingiu o limite de perguntas. Tente mais tarde.",
  MENTORIA_RATE_LIMIT_UNAVAILABLE: "Serviço temporariamente indisponível.",
  MENTORIA_ORIGIN_INVALID: "Esta página não está autorizada a conversar com o assistente.",
};

export function mentoriaAssistantConfig() {
  const privacyUrl = securePrivacyUrl(import.meta.env.VITE_MENTORIA_PRIVACY_URL);
  return {
    enabled: import.meta.env.VITE_MENTORIA_ASSISTANT_ENABLED === "true" && Boolean(privacyUrl),
    privacyUrl,
  };
}

/**
 * Questions exist only in component memory. There are no lead creation,
 * payments, grants, privileged sessions or persistent chat history here.
 */
export default function MentoriaAssistant() {
  const config = mentoriaAssistantConfig();
  const [items, setItems] = useState<ConversationItem[]>([]);
  const idSequence = useRef(0);
  const [message, setMessage] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [temporarilyUnavailable, setTemporarilyUnavailable] = useState(false);

  if (!config.enabled || !config.privacyUrl) return null;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const question = message.trim();
    if (!acknowledged || busy || temporarilyUnavailable || question.length < 3 || question.length > 500) return;

    setBusy(true);
    setError("");
    setItems((current) => [...current, { id: ++idSequence.current, author: "visitor", text: question }]);
    setMessage("");

    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 17000);
    try {
      const base = publicEnv("VITE_API_BASE_URL").replace(/\/$/, "");
      const response = await fetch(`${base}/api/v2/public/mentoria/assistant`, {
        method: "POST",
        credentials: "omit",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          message: question,
          ai_processing_acknowledged: true,
          no_sensitive_data_acknowledged: true,
        }),
      });
      if (response.status !== 200) {
        let code = "";
        try {
          const payload = (await response.json()) as { detail?: unknown };
          if (typeof payload.detail === "string") code = payload.detail;
        } catch {
          // Never render arbitrary server errors in a public UI.
        }
        if (response.status === 503) setTemporarilyUnavailable(true);
        throw new Error(ERROR_MESSAGES[code] || "Não foi possível responder agora.");
      }
      const payload = (await response.json()) as ReplyPayload;
      if (typeof payload.reply !== "string" || payload.reply.length < 1 || payload.reply.length > 1200
          || !["catalog", "ai"].includes(String(payload.source))) {
        throw new Error("Resposta inválida do assistente. Tente mais tarde.");
      }
      setItems((current) => [...current, {
        id: ++idSequence.current, author: "assistant", text: payload.reply as string,
      }]);
    } catch (cause) {
      setError(cause instanceof Error && cause.name === "AbortError"
        ? "A resposta excedeu o tempo limite. Tente novamente mais tarde."
        : cause instanceof Error ? cause.message : "Erro de conexão com o assistente.");
    } finally {
      window.clearTimeout(timeout);
      setBusy(false);
    }
  }

  return (
    <section className="dg-mentor-ai" aria-labelledby="dg-mentor-ai-heading">
      <div className="dg-mentor-ai__heading">
        <span className="dg-mentoria__kicker">Orientação inicial</span>
        <h2 id="dg-mentor-ai-heading">Converse com o assistente da mentoria.</h2>
        <p>Uma IA para ajudar a entender o programa e explorar aplicações nos negócios. Não é atendimento humano.</p>
      </div>
      <div className="dg-mentor-ai__panel">
        <div className="dg-mentor-ai__intro">
          <span aria-hidden="true" className="dg-mentor-ai__avatar">IA</span>
          <div>
            <strong>Assistente da Mentoria IA para Negócios</strong>
            <small>Responde com base na proposta oficial, sem prometer resultados ou confirmar matrículas.</small>
          </div>
        </div>
        <div className="dg-mentor-ai__conversation" aria-live="polite" aria-relevant="additions text">
          <div className="dg-mentor-ai__bubble dg-mentor-ai__bubble--assistant">
            Olá! Posso explicar como a mentoria funciona ou sugerir caminhos seguros para aplicar IA na sua empresa.
          </div>
          {items.map((item) => (
            <div key={item.id} className={`dg-mentor-ai__bubble dg-mentor-ai__bubble--${item.author}`}>
              {item.text}
            </div>
          ))}
          {busy && <p className="dg-mentor-ai__thinking" role="status">Preparando resposta…</p>}
        </div>
        {items.length === 0 && (
          <div className="dg-mentor-ai__suggestions" aria-label="Sugestões de perguntas">
            {STARTERS.map((question) => (
              <button type="button" key={question}
                onClick={() => setMessage(question)}
                disabled={busy || temporarilyUnavailable}>
                {question}
              </button>
            ))}
          </div>
        )}
        <form onSubmit={submit} className="dg-mentor-ai__form">
          <label htmlFor="dg-mentor-ai-question">Sua pergunta</label>
          <textarea id="dg-mentor-ai-question" value={message}
            minLength={3} maxLength={500} rows={2}
            placeholder="Ex.: Por onde começar com IA no meu negócio?"
            onChange={(event) => setMessage(event.target.value)}
            disabled={busy || temporarilyUnavailable} required />
          <label className="dg-mentor-ai__consent">
            <input type="checkbox" checked={acknowledged}
              onChange={(event) => setAcknowledged(event.target.checked)}
              disabled={busy || temporarilyUnavailable} />
            <span>Estou ciente de que minha pergunta será processada por IA. Não incluirei dados pessoais, de clientes ou informações confidenciais. Consulte a <a
              href={config.privacyUrl} target="_blank" rel="noopener noreferrer">Política de Privacidade</a>.</span>
          </label>
          <div className="dg-mentor-ai__bottom">
            <span>Não envie senhas ou documentos. Este chat não realiza cadastro nem pagamentos.</span>
            <button type="submit" disabled={busy || !acknowledged || temporarilyUnavailable
                || message.trim().length < 3 || message.length > 500}>
              {busy ? "Enviando…" : "Perguntar à IA"}
            </button>
          </div>
          {error && <p className="dg-mentor-ai__error" role="alert">{error}</p>}
        </form>
        <div className="dg-mentor-ai__cta">
          <span>Quer participar do primeiro encontro?</span>
          <a href="#workshop">Ir para o cadastro do workshop</a>
        </div>
      </div>
    </section>
  );
}
