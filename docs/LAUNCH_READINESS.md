# Launch readiness

The application remains a local development build. No deployment or custom domain has been configured in this repository.

## Required before public launch

- Connect and verify an organization-approved custom domain at the chosen frontend host. Set the production API origin and canonical URL to that domain. Configure HTTPS and verify frontend-to-backend access.
- Complete Supabase production setup, confirm Row Level Security is enabled on the app tables, create the initial administrator, and verify role access with separate accounts. Never deploy with `APP_MODE=local`.
- Review the in-app Privacy Policy and Terms and Conditions pages with the university. They are explicitly drafts and require the responsible entity, verified contact, jurisdiction, retention/deletion practices, and any institution-specific terms.
- Verify favicon visibility on the deployed host and check page titles, descriptions, mobile navigation, and every public route on the final domain.
- Confirm production data flows, backups, retention, and access controls. Do not present simulator output as actual readings or estimated savings as verified results.

## Current repository state

- A custom SVG favicon is in `frontend/public/favicon.svg` and is linked from `frontend/index.html`.
- Privacy Policy and Terms and Conditions routes are available from the footer. Their content is a launch draft, not legal advice or institution-approved policy.
- The app has no customer reviews or testimonials, AI-generated stock photos, or AI attribution badge.
- No custom domain, cloud deployment, production Supabase project, or live meter source is configured here. Local preview is not production launch approval.
