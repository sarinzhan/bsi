/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "mock": run the UI on in-memory data, without a backend. */
  readonly VITE_API?: string;
}
