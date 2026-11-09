/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_MENTORIA_WORKSHOP_URL?: string;
  readonly VITE_MENTORIA_REGISTRATION_ENABLED?: string;
  readonly VITE_MENTORIA_ASSISTANT_ENABLED?: string;
  readonly VITE_MENTORIA_PRIVACY_URL?: string;
  readonly VITE_MENTORIA_PRIVACY_VERSION?: string;
  readonly VITE_STREAM_TIMEOUT_MS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
