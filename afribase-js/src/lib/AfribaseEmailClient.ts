import { fetchWithAuth, handleResponse } from './fetch';

export interface SendEmailOptions {
  /** Recipient email address. */
  to: string;
  /** ID of a saved custom template (created in the Afribase dashboard). */
  template_id?: string;
  /** Variables substituted as {{ .Key }} inside the template subject and body. */
  template_vars?: Record<string, string>;
  /** Email subject — required when not using template_id. */
  subject?: string;
  /** HTML email body — required when not using template_id. */
  html?: string;
  /** Override the from address (defaults to SMTP admin email). */
  from?: string;
  /** Override the sender display name. */
  from_name?: string;
}

export interface EmailTemplate {
  id: string;
  name: string;
  description?: string;
  subject: string;
  html: string;
  created_at: string;
  updated_at: string;
}

/**
 * AfribaseEmailClient — send transactional emails from your app using your
 * project's configured SMTP provider, without any additional setup.
 *
 * @example
 * // With a saved template
 * await afribase.email.send({
 *   to: 'user@example.com',
 *   template_id: 'welcome',
 *   template_vars: { name: 'John', plan: 'Pro' },
 * });
 *
 * // Raw send (no template)
 * await afribase.email.send({
 *   to: 'user@example.com',
 *   subject: 'Hello from MyApp',
 *   html: '<h1>Hello John!</h1>',
 * });
 */
export class AfribaseEmailClient {
  private readonly emailUrl: string;
  private readonly slug: string;
  private readonly apiKey: string;
  private readonly getAccessToken: () => string | null;
  private readonly customFetch?: typeof fetch;

  constructor(options: {
    baseUrl: string;
    slug: string;
    apiKey: string;
    getAccessToken: () => string | null;
    customFetch?: typeof fetch;
  }) {
    this.emailUrl = `${options.baseUrl.replace(/\/$/, '')}/email/v1`;
    this.slug = options.slug;
    this.apiKey = options.apiKey;
    this.getAccessToken = options.getAccessToken;
    this.customFetch = options.customFetch;
  }

  /**
   * Send a transactional email.
   *
   * Uses your project's configured SMTP provider. Falls back to the
   * Afribase platform mailer if no custom SMTP is configured.
   */
  async send(options: SendEmailOptions): Promise<{ data: { status: string } | null; error: any }> {
    const resp = await fetchWithAuth(`${this.emailUrl}/${this.slug}/send`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(options),
      apiKey: this.apiKey,
      accessToken: this.getAccessToken(),
      customFetch: this.customFetch,
    });
    return handleResponse(resp);
  }

  /**
   * List all custom email templates created in the Afribase dashboard for this project.
   */
  async listTemplates(): Promise<{ data: EmailTemplate[] | null; error: any }> {
    const resp = await fetchWithAuth(`${this.emailUrl}/${this.slug}/templates`, {
      method: 'GET',
      apiKey: this.apiKey,
      accessToken: this.getAccessToken(),
      customFetch: this.customFetch,
    });
    return handleResponse(resp);
  }
}
