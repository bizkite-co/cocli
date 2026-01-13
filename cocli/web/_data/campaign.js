const fs = require('fs');
const path = require('path');
const toml = require('@iarna/toml');

module.exports = () => {
  const campaignName = process.env.CAMPAIGN || 'turboship';
  
  // Try to find the local config.toml for this campaign to pull defaults
  // Assuming we are in cocli/web/_data/ and config is in cocli_data/campaigns/<name>/config.toml
  let configFromFile = {};
  const dataHome = process.env.COCLI_DATA_HOME || path.join(process.env.HOME, '.local/share/cocli_data');
  const configPath = path.join(dataHome, 'campaigns', campaignName, 'config.toml');

  if (fs.existsSync(configPath)) {
    try {
      const content = fs.readFileSync(configPath, 'utf8');
      const parsed = toml.parse(content);
      configFromFile = parsed.aws || {};
    } catch (e) {
      console.error(`Error reading config.toml at ${configPath}:`, e);
    }
  }

  return {
    name: campaignName,
    userPoolId: process.env.COCLI_USER_POOL_ID || configFromFile.cocli_user_pool_id || '',
    userPoolClientId: process.env.COCLI_USER_POOL_CLIENT_ID || configFromFile.cocli_user_pool_client_id || '',
    identityPoolId: process.env.COCLI_IDENTITY_POOL_ID || configFromFile.cocli_identity_pool_id || '',
    region: process.env.AWS_REGION || configFromFile.region || 'us-east-1',
    commandQueueUrl: process.env.COCLI_COMMAND_QUEUE_URL || configFromFile.cocli_command_queue_url || ''
  };
};
