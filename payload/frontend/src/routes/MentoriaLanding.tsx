import React, { useEffect } from "react";
import { Link } from "react-router-dom";
import "./MentoriaLanding.css";
import WorkshopRegistrationForm, { registrationFormConfig } from "./WorkshopRegistrationForm";

/**
 * M0 is intentionally presentation-only.
 * Workshop registration is delegated to an explicitly configured HTTPS URL.
 * No payment, enrollment, session, tenant or access grant is created here.
 */
export function workshopRegistrationUrl(configuredValue: string | undefined): string | null {
  const value = (configuredValue ?? "").trim();
  if (!value) return null;

  try {
    const url = new URL(value);
    // The public CTA must not become a javascript: or insecure redirect.
    if (url.protocol !== "https:" || !url.hostname || url.username || url.password) {
      return null;
    }
    return url.toString();
  } catch {
    return null;
  }
}

const TOPICS = [
  {
    number: "01",
    title: "Onde a IA cria valor",
    description:
      "Mapeie tarefas repetitivas, decisões e oportunidades de produtividade antes de escolher ferramentas.",
  },
  {
    number: "02",
    title: "Segurança e governança",
    description:
      "Entenda os cuidados com dados de clientes, revisão humana, permissões e informações estratégicas.",
  },
  {
    number: "03",
    title: "Retorno que pode ser medido",
    description:
      "Defina indicadores, custos e critérios para avaliar o impacto real de um projeto de IA.",
  },
] as const;

const FAQ = [
  {
    question: "Preciso saber programar?",
    answer:
      "Não. A mentoria é direcionada a empresários e gestores. O foco é a aplicação da IA aos processos do negócio.",
  },
  {
    question: "Qual é o formato da mentoria?",
    answer:
      "A proposta contempla 6 horas de encontros coletivos ao vivo e 1 hora individual posterior por participante. Datas e condições serão divulgadas na abertura das inscrições.",
  },
  {
    question: "O acesso à plataforma PatroAI está incluído?",
    answer:
      "As condições de acesso, quando aplicáveis, serão informadas na oferta oficial. A mentoria não equivale automaticamente à contratação da plataforma.",
  },
  {
    question: "A mentoria garante aumento de receita?",
    answer:
      "Não. O objetivo é construir critérios e um plano de aplicação. Os resultados dependem do contexto e da execução de cada empresa.",
  },
] as const;

export default function MentoriaLanding() {
  const formEnabled = registrationFormConfig().enabled;
  const registrationUrl = workshopRegistrationUrl(
    import.meta.env.VITE_MENTORIA_WORKSHOP_URL,
  );

  useEffect(() => {
    const previousTitle = document.title;
    document.title = "Mentoria IA para Negócios | Daniel Graebin";
    return () => {
      document.title = previousTitle;
    };
  }, []);

  return (
    <main id="main-content" className="dg-mentoria">
      <div className="dg-mentoria__ambient" aria-hidden="true" />
      <header className="dg-mentoria__header">
        <div className="dg-mentoria__container dg-mentoria__header-inner">
          <Link className="dg-mentoria__brand" to="/mentoria" aria-label="Daniel Graebin — início da mentoria">
            <span className="dg-mentoria__brand-mark" aria-hidden="true">DG</span>
            <span className="dg-mentoria__brand-text">
              <strong>Daniel Graebin</strong>
              <small>IA para negócios</small>
            </span>
          </Link>
          <nav className="dg-mentoria__nav" aria-label="Navegação da mentoria">
            <a href="#metodo">O método</a>
            <a href="#programa">A mentoria</a>
            <a href="#duvidas">Dúvidas</a>
            <Link to="/mentoria/area">Área do mentorado</Link>
            <a className="dg-mentoria__nav-cta" href="#workshop">Workshop</a>
          </nav>
        </div>
      </header>

      <section className="dg-mentoria__hero dg-mentoria__container" aria-labelledby="dg-hero-title">
        <div className="dg-mentoria__hero-content">
          <div className="dg-mentoria__eyebrow"><span className="dg-mentoria__pulse" /> Mentoria para quem lidera empresas</div>
          <h1 id="dg-hero-title">
            A inteligência artificial só faz sentido quando
            <em> faz diferença no seu negócio.</em>
          </h1>
          <p className="dg-mentoria__lead">
            Descubra como identificar oportunidades, aplicar IA com segurança e
            medir resultados — sem precisar se tornar desenvolvedor.
          </p>
          <div className="dg-mentoria__hero-actions">
            <a className="dg-mentoria__button dg-mentoria__button--primary" href="#workshop">
              Conhecer o workshop <span aria-hidden="true">↗</span>
            </a>
            <a className="dg-mentoria__text-link" href="#programa">
              Ver o formato da mentoria <span aria-hidden="true">↓</span>
            </a>
          </div>
          <p className="dg-mentoria__hero-note">
            Uma experiência conduzida por quem aplica IA no próprio negócio.
          </p>
        </div>
        <div className="dg-mentoria__hero-art" aria-label="Três prioridades da mentoria: estratégia, segurança e resultado">
          <div className="dg-mentoria__orbit dg-mentoria__orbit--one" aria-hidden="true" />
          <div className="dg-mentoria__orbit dg-mentoria__orbit--two" aria-hidden="true" />
          <div className="dg-mentoria__art-core">
            <span className="dg-mentoria__art-monogram">DG</span>
            <span>INTELIGÊNCIA APLICADA</span>
          </div>
          <span className="dg-mentoria__art-label dg-mentoria__art-label--one">Estratégia</span>
          <span className="dg-mentoria__art-label dg-mentoria__art-label--two">Segurança</span>
          <span className="dg-mentoria__art-label dg-mentoria__art-label--three">Resultado</span>
        </div>
      </section>

      <section className="dg-mentoria__belief">
        <div className="dg-mentoria__container dg-mentoria__belief-inner">
          <p>Mais ferramentas não significam mais resultados.</p>
          <strong>O próximo passo é aprender a usar IA com intenção, método e responsabilidade.</strong>
        </div>
      </section>

      <section id="metodo" className="dg-mentoria__section dg-mentoria__container" aria-labelledby="dg-method-title">
        <div className="dg-mentoria__section-heading">
          <span className="dg-mentoria__kicker">O que você vai aprender</span>
          <h2 id="dg-method-title">Menos improviso. <span>Mais clareza para decidir.</span></h2>
          <p>O ponto de partida são os desafios do seu negócio, não uma lista interminável de ferramentas.</p>
        </div>
        <div className="dg-mentoria__topics">
          {TOPICS.map((topic) => (
            <article className="dg-mentoria__topic" key={topic.number}>
              <span className="dg-mentoria__topic-number">{topic.number}</span>
              <h3>{topic.title}</h3>
              <p>{topic.description}</p>
              <span className="dg-mentoria__topic-bar" aria-hidden="true" />
            </article>
          ))}
        </div>
      </section>

      <section className="dg-mentoria__section dg-mentoria__story">
        <div className="dg-mentoria__container dg-mentoria__story-grid">
          <div>
            <span className="dg-mentoria__kicker">Experiência por trás do método</span>
            <h2>Eu precisei ir além das ferramentas prontas.</h2>
          </div>
          <div className="dg-mentoria__story-copy">
            <p>
              Sou Daniel Graebin. Há mais de três anos utilizo inteligência artificial
              no meu negócio e desenvolvi minha própria plataforma para atender
              necessidades que as soluções genéricas não resolviam.
            </p>
            <p>
              Quero compartilhar o que aprendi na prática: como escolher aplicações,
              reconhecer limites, proteger informações e avaliar o retorno das iniciativas.
              A tecnologia é um meio. O negócio é o objetivo.
            </p>
            <span className="dg-mentoria__signature">Daniel Graebin <small>Mentor e fundador da PatroAI</small></span>
          </div>
        </div>
      </section>

      <section id="programa" className="dg-mentoria__section dg-mentoria__container" aria-labelledby="dg-program-title">
        <div className="dg-mentoria__program">
          <div className="dg-mentoria__program-copy">
            <span className="dg-mentoria__kicker">A mentoria</span>
            <h2 id="dg-program-title">Conhecimento coletivo. <span>Direção individual.</span></h2>
            <p>
              Uma jornada para sair dos testes isolados e construir um plano
              de aplicação de inteligência artificial alinhado à sua empresa.
            </p>
            <ul>
              <li>Exemplos e exercícios conectados a processos de negócio.</li>
              <li>Cuidados com segurança, qualidade e revisão humana.</li>
              <li>Critérios de priorização e mensuração de resultados.</li>
              <li>Uma conversa individual sobre seu próximo passo.</li>
            </ul>
          </div>
          <div className="dg-mentoria__hours" aria-label="Formato previsto da mentoria">
            <div><strong>6<span>h</span></strong><p>Encontros coletivos ao vivo</p></div>
            <div><strong>1<span>h</span></strong><p>Sessão individual posterior</p></div>
            <p className="dg-mentoria__hours-note">Datas, valor e condições serão confirmados antes da abertura de vendas.</p>
          </div>
        </div>
      </section>

      <div className="dg-mentoria__container">
        <MentoriaAssistant />
      </div>

      <section id="workshop" className="dg-mentoria__section dg-mentoria__workshop" aria-labelledby="dg-workshop-title">
        <div className="dg-mentoria__container dg-mentoria__workshop-inner">
          <div>
            <span className="dg-mentoria__kicker">Primeiro encontro</span>
            <h2 id="dg-workshop-title">Tudo começa com um workshop online.</h2>
            <p>
              Entenda onde a IA pode gerar valor na sua empresa, os principais
              cuidados para começar e como avaliar se vale investir.
            </p>
          </div>
          <div className="dg-mentoria__workshop-action">
            {formEnabled ? (
              <WorkshopRegistrationForm />
            ) : registrationUrl ? (
              <a
                className="dg-mentoria__button dg-mentoria__button--primary"
                href={registrationUrl}
                target="_blank"
                rel="noopener noreferrer"
              >
                Ir para a inscrição <span aria-hidden="true">↗</span>
              </a>
            ) : (
              <div className="dg-mentoria__coming-soon" role="status">
                <strong>Inscrições em preparação</strong>
                <span>O link oficial será disponibilizado aqui quando as inscrições abrirem.</span>
              </div>
            )}
            <small>O workshop antecede a oferta da mentoria.</small>
          </div>
        </div>
      </section>

      <section id="duvidas" className="dg-mentoria__section dg-mentoria__container dg-mentoria__faq" aria-labelledby="dg-faq-title">
        <div className="dg-mentoria__section-heading">
          <span className="dg-mentoria__kicker">Perguntas frequentes</span>
          <h2 id="dg-faq-title">Antes de começar.</h2>
        </div>
        <div className="dg-mentoria__faq-list">
          {FAQ.map(({ question, answer }) => (
            <details key={question}>
              <summary>{question}<span aria-hidden="true">+</span></summary>
              <p>{answer}</p>
            </details>
          ))}
        </div>
      </section>

      <footer className="dg-mentoria__footer">
        <div className="dg-mentoria__container dg-mentoria__footer-inner">
          <span><strong>DG.</strong> Mentoria IA para Negócios</span>
          <span>Uma iniciativa de Daniel Graebin • Tecnologia a serviço do negócio.</span>
          <Link to="/">Conhecer a EFATÀ 777</Link>
        </div>
      </footer>
    </main>
  );
}
