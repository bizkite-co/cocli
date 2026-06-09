---
layout: layout.njk
title: Authenticating...
---

<div class="auth-container">
    <h1>Authenticating...</h1>
    <div id="auth-status">Please wait while we complete your sign-in.</div>
</div>

<script>
    (function() {
        console.log("Auth callback started. Hash:", window.location.hash ? "present" : "missing");
        const hash = window.location.hash.substring(1);
        const params = new URLSearchParams(hash);
        const idToken = params.get('id_token');
        const accessToken = params.get('access_token');

        function parseJwt(token) {
            try {
                const base64Url = token.split('.')[1];
                const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
                const jsonPayload = decodeURIComponent(atob(base64).split('').map(c =>
                    '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)
                ).join(''));
                return JSON.parse(jsonPayload);
            } catch (e) {
                console.error('JWT Parse Error:', e);
                return null;
            }
        }

        const hostname = window.location.hostname;
        const domainSuffix = hostname.endsWith('turboheat.net') ? '; domain=.turboheat.net' : '';
        const secureSuffix = window.location.protocol === 'https:' ? '; Secure' : '';

        function setAuthCookie(name, value, days = 7) {
            const date = new Date();
            date.setTime(date.getTime() + (days * 24 * 60 * 60 * 1000));
            const expires = "; expires=" + date.toUTCString();
            document.cookie = name + "=" + (value || "") + expires + "; path=/" + domainSuffix + secureSuffix + "; SameSite=Lax";
        }

        if (idToken) {
            console.log("Tokens found, storing in localStorage and cookies...");
            localStorage.setItem('cocli_id_token', idToken);
            localStorage.setItem('cocli_access_token', accessToken);
            
            const payload = parseJwt(idToken);
            const username = payload ? (payload.email || payload.preferred_username || payload['cognito:username'] || 'User') : 'User';

            setAuthCookie('cognito_id_token', idToken, 7);
            setAuthCookie('cognito_access_token', accessToken, 7);
            setAuthCookie('is_logged_in', 'true', 7);
            setAuthCookie('user_email', username, 7);

            // Clear the hash to avoid it hanging around in history
            window.history.replaceState(null, null, window.location.pathname);
            
            console.log("Redirecting to dashboard...");
            window.location.href = '/index.html';
        } else {
            const urlParams = new URLSearchParams(window.location.search);

            const error = urlParams.get('error');
            if (error) {
                console.error("Auth error:", error);
                document.getElementById('auth-status').innerHTML = '<span class="error" style="color:red">Authentication error: ' + error + '</span>';
            } else {
                console.warn("No tokens and no error. Hash was:", window.location.hash);
                document.getElementById('auth-status').textContent = 'Authentication failed. No tokens received.';
            }
        }
    })();
</script>
