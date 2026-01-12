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
        const hash = window.location.hash.substring(1);
        const params = new URLSearchParams(hash);
        const idToken = params.get('id_token');
        const accessToken = params.get('access_token');

        if (idToken) {
            localStorage.setItem('cocli_id_token', idToken);
            localStorage.setItem('cocli_access_token', accessToken);
            window.location.href = '/index.html';
        } else {
            // Check for authorization code (not using yet but good for future)
            const urlParams = new URLSearchParams(window.location.search);
            const error = urlParams.get('error');
            if (error) {
                document.getElementById('auth-status').innerHTML = '<span class="error">Authentication error: ' + error + '</span>';
            } else {
                // If we reach here without tokens and no error in URL, maybe we need to redirect to login
                document.getElementById('auth-status').textContent = 'No tokens found. Redirecting to login...';
                // Trigger login flow if needed
            }
        }
    })();
</script>
