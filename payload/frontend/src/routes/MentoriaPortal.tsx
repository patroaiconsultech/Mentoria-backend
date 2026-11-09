import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, apiJson } from "../api";
import "./MentoriaPortal.css";

type AuthorizedCohort = {
  cohort_id: string;
  program_title: string;
  starts_at: string;
  ends_at: string;
  timezone_name: string;
  access_expires_at: string;
};
type PortalResponse = { programs: AuthorizedCohort[] };
type PortalState =
  | { state: "loading" }
  | { state: "ready"; programs: AuthorizedCohort[] }
  | { state: "login" }
  | { state: "denied" }
  | { state: "disabled" }
  | { state: "error" };

function formatDate(value: string, zone: string): string {
  const instant = new Date(value);
  if (!Number.isFinite(instant.valueOf())) return "Data a confirmar";
  try {
    return new Intl.DateTimeFormat("pt-BR", {
      dateStyle: "medium",
      timeZone: zone || "America/Sao_Paulo",
    }).format(instant);
  } catch {
    return "Data a confirmar";
  }
}

export default function MentoriaPortal() {
  const [status, setStatus] = useState<PortalState>({ state: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setStatus({ state: "loading" });
    apiJson<PortalResponse>("/api/v2/mentoria/portal/me")
      .then((response) => {
        if (!active) return;
        if (!response || !Array.isArray(response.programs)) {
          setStatus({ state: "error" });
          return;
        }
        setStatus({ state: "ready", programs: response.programs });
      })
      .catch((error: unknown) => {
        if (!active) return;
        const code = error instanceof ApiError ? error.status : 0;
        setStatus({
          state: code === 401 ? "login" :
            code === 403 ? "denied" :
            code === 503 ? "disabled" : "error",
        });
      });
    return () => { active = false; };
  }, [attempt]);

  return (
    <main className="dg-portal" id="main-content">
      <header className="dg-portal__header">
        <Link className="dg-portal__brand" to="/mentoria">DG <span>Mentoria IA para Negócios</span></Link>
        <Link to="/mentoria">Voltar à apresentação</Link>
      </header>
      <div className="dg-portal__container">
        <p className="dg-portal__eyebrow">ÁREA DO MENTORADO</p>
        <h1>Seu espaço para transformar conhecimento em ação.</h1>
        <p className="dg-portal__subtitle">
          Suas turmas autorizadas são consultadas diretamente no servidor a cada acesso.
        </p>

        {status.state === "loading" && (
          <section className="dg-portal__notice" role="status">Verificando sua matrícula e as permissões de acesso…</section>
        )}
        {status.state === "login" && (
          <section className="dg-portal__notice" role="alert">
            <h2>É necessário entrar na sua conta.</h2>
            <p>O acesso depende de uma sessão válida e de uma matrícula vinculada à sua identidade.</p>
            <Link className="dg-portal__button" to="/access?next=%2Fmentoria%2Farea">Entrar com minha conta</Link>
          </section>
        )}
        {status.state === "denied" && (
          <section className="dg-portal__notice" role="alert">
            <h2>Acesso ainda não autorizado.</h2>
            <p>Não encontramos uma identidade de mentorado verificada para esta sessão. Nenhuma matrícula é criada automaticamente.</p>
            <Link className="dg-portal__button" to="/mentoria">Conhecer a mentoria</Link>
          </section>
        )}
        {status.state === "disabled" && (
          <section className="dg-portal__notice" role="status">
            <h2>Área do mentorado em preparação.</h2>
            <p>O portal privado ainda não foi habilitado nesta implantação.</p>
          </section>
        )}
        {status.state === "error" && (
          <section className="dg-portal__notice" role="alert">
            <h2>Não conseguimos consultar seu acesso agora.</h2>
            <p>Nenhuma autorização foi presumida. Você pode tentar novamente.</p>
            <button className="dg-portal__button" type="button" onClick={() => setAttempt((n) => n + 1)}>
              Tentar novamente
            </button>
          </section>
        )}
        {status.state === "ready" && status.programs.length === 0 && (
          <section className="dg-portal__notice" role="status">
            <h2>Nenhuma turma ativa disponível.</h2>
            <p>Quando houver uma matrícula e um acesso válidos, sua turma aparecerá aqui.</p>
            <Link className="dg-portal__button" to="/mentoria">Conhecer o programa</Link>
          </section>
        )}
        {status.state === "ready" && status.programs.length > 0 && (
          <section className="dg-portal__courses" aria-label="Turmas com acesso autorizado">
            {status.programs.map((program) => (
              <article className="dg-portal__course" key={program.cohort_id}>
                <div className="dg-portal__pill">Matrícula ativa</div>
                <h2>{program.program_title}</h2>
                <dl>
                  <div><dt>Início</dt><dd>{formatDate(program.starts_at, program.timezone_name)}</dd></div>
                  <div><dt>Término previsto</dt><dd>{formatDate(program.ends_at, program.timezone_name)}</dd></div>
                  <div><dt>Acesso até</dt><dd>{formatDate(program.access_expires_at, program.timezone_name)}</dd></div>
                </dl>
                <p className="dg-portal__placeholder">
                  Agenda detalhada, materiais e gravações serão disponibilizados aqui após a publicação oficial.
                </p>
              </article>
            ))}
          </section>
        )}
      </div>
    </main>
  );
}
