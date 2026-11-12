/**
 * Global shared frontend types for VERITAS.
 */

export interface User {
  id: string;
  email: string;
  full_name: string;
  phone_number?: string | null;
  role: 'SUPER_ADMIN' | 'MERCHANT_ADMIN' | 'USER' | 'AUDITOR';
  whatsapp_opt_in: boolean;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

