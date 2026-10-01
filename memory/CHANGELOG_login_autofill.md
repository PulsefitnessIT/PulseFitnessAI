# Login autofill fix — /login page (2026-06)

Video showed iCloud Passwords (Edge) filling the EMAIL but leaving PASSWORD empty on /login.
Root cause: the previous autofill fixes covered PulseLandingPage/CRMLogin/MODServiceLogin/StaffLogin
but MISSED /app/frontend/src/pages/LoginPage.js (the /login route in the video). Its email used
autocomplete="email" (not "username") and the password input had NO name/id/autocomplete — so
managers matched the account to the username but couldn't identify the password field.

Fix (LoginPage.js):
- email input: name="username", id="username", autocomplete="username" (was autocomplete="email", no name/id)
- password input: name="password", id="current-password", autocomplete="current-password" (previously none)
Both already sit in the same <form>. Verified in live preview DOM.

Requires redeploy to reach production (video was from production with the old markup).
