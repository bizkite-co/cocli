module.exports = function(eleventyConfig) {
  // Pass through the CSS and any other assets
  eleventyConfig.addPassthroughCopy("style.css");
  eleventyConfig.addPassthroughCopy("theme.css");
  eleventyConfig.addPassthroughCopy("dashboard.js");
  eleventyConfig.addPassthroughCopy("config_dashboard.js");
  eleventyConfig.addPassthroughCopy("papaparse.min.js");

  // Global data for environment variables
  eleventyConfig.addGlobalData("env", process.env);
  
  // Set custom input and output directories
  return {
    dir: {
      input: ".",
      output: "../../build/web",
      includes: "_includes"
    }
  };
};
