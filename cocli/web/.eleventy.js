module.exports = function(eleventyConfig) {
  // Pass through the CSS and any other assets
  eleventyConfig.addPassthroughCopy("style.css");
  eleventyConfig.addPassthroughCopy("dashboard.js");
  eleventyConfig.addPassthroughCopy("kml-viewer.html");

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
