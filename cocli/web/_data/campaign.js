const fs = require('fs');
const path = require('path');

module.exports = () => {
  const campaignName = process.env.CAMPAIGN || 'turboship';
  
  // We can't easily read the TOML here without more dependencies,
  // but we can rely on environment variables passed by cocli/commands/web.py
  return {
    name: campaignName,
    userPoolId: process.env.COCLI_USER_POOL_ID || '',
    userPoolClientId: process.env.COCLI_USER_POOL_CLIENT_ID || '',
    identityPoolId: process.env.COCLI_IDENTITY_POOL_ID || '',
    region: process.env.AWS_REGION || 'us-east-1',
    commandQueueUrl: process.env.COCLI_COMMAND_QUEUE_URL || ''
  };
};
