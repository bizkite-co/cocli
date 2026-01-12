---
layout: layout.njk
title: Signed Out
---

<div class="auth-container">
    <h1>You have been signed out.</h1>
    <p>Your session has ended successfully.</p>
    <a href="/index.html" class="btn btn-primary">Go to Dashboard</a>
</div>

<script>
    // Clear any local session indicators if we add them later
    localStorage.removeItem('cocli_session');
</script>
