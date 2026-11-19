# Multiple business workspaces

Registered businesses can use **Add another business** in their dashboard, My Accounts, or the business registration page. A new workspace gets its own company profile, business ID, jobs, coupons and wallet. The original business is unchanged. Users switch through POST forms in the business selector.

ManagedBusiness connects the login owner to an isolated business account with an unusable password. No extra phone login or password is created. Access requires a server-session owner grant bound to the owner's authentication hash; changing the owner's password or deactivating the owner invalidates workspace access. A managed account cannot be entered by directly authenticating as that account. Switches require CSRF and ownership checks. Form tokens expire after one hour and duplicate submissions reuse the original workspace.

Super Admin Delete Everything includes owned managed businesses in the review plan. Legacy deletion protects owners with managed businesses. Shared records belonging to other users retain the existing preservation rules.

Deployment requires jobs migration 0063_managed_business. Existing accounts do not need a data migration. Do not create synthetic business accounts in production for deployment checks.
