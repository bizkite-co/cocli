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

        if (idToken) {
            console.log("Tokens found, storing in localStorage...");
            localStorage.setItem('cocli_id_token', idToken);
            localStorage.setItem('cocli_access_token', accessToken);
            
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
