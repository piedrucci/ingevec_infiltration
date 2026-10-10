# Google sign-in through Keycloak

The web app and Superset already authenticate through Keycloak. Add Google as a
Keycloak identity provider; do not replace the realm users or create parallel
application accounts. Keep the Keycloak password form available while testing.

## Google OAuth clients

Create a Google Cloud OAuth client of type **Web application**. Since the
development and production Keycloak realms use different hostnames, create a
separate OAuth client for each environment (or register both callback URIs on
one client if that is preferred).

Register these Authorized redirect URIs:

| Environment | Google callback URI |
| --- | --- |
| Development | `http://localhost:8080/realms/ingevec-development/broker/google/endpoint` |
| Production | `https://auth.capix.cloud/realms/ingevec-production/broker/google/endpoint` |

The callback is Keycloak’s broker endpoint. The app and Superset continue to
use their existing Keycloak client redirect URIs.

Google needs the OAuth client ID and secret. Keep the secret in a password
manager or enter it directly in the matching Keycloak realm. Do not commit it
to Git or paste it into chat. For initial testing, configure the Google OAuth
consent screen as External and add the tester Google accounts to its test-user
list. Google may require verification before an externally available app can
move out of testing.

## Configure the development realm

1. Open the Keycloak Admin Console at `http://localhost:8080` and select the
   `ingevec-development` realm.
2. Go to **Identity providers**, choose **Google**, and enter the development
   client ID and secret.
3. Enable the provider. Keep the standard scopes `openid profile email`.
   Leave **Trust email** off and retain the default **First login flow** so
   Keycloak asks the user to authenticate the existing Keycloak account before
   linking it. Do not enable automatic account linking.
4. Leave **Default Identity Provider** unset during the rollout. The login
   page will offer Google while retaining the password form as a fallback.
5. Test with an existing development user. Use an exact matching, verified
   Google email and complete Keycloak’s existing-account confirmation. Check
   the user’s Keycloak ID, realm roles, groups, app access, and Superset login
   before moving on.

If the Google identity does not match an existing Keycloak user, stop and
inspect the first-login flow and email attributes. Do not approve a newly
created account as a workaround. New broker users do not inherit application
or Superset roles automatically.

## Link existing users

For each existing user, link Google to the existing Keycloak account using
Keycloak’s first-login account verification flow. The user verifies their
current Keycloak credentials, then Keycloak attaches the Google identity to
that account. This preserves the existing Keycloak subject used by the API and
Superset, along with the user’s role and group assignments.

Test first with `piedrucci@gmail.com` in development. Verify the Keycloak user
ID before and after linking, then verify the web app’s administrator access and
the embedded dashboard. Keep an administrator account with a working password
available throughout the rollout.

## Production rollout

After development works, repeat the provider setup in the `ingevec-production`
realm with the production Google OAuth credentials. Add the production Google
accounts to the OAuth consent screen if it is still in testing. Link and verify
existing production accounts one at a time. Keep the password form and an
administrator password login available until every user and the Superset
dashboard have been confirmed.

Only after the rollout is verified should you set Google as the realm’s
**Default Identity Provider**. Keep a tested way for administrators to reach
the password form for recovery before making that change.
