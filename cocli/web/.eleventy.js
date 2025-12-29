module.exports = function(eleventyConfig) {
  // Pass through the CSS and any other assets
  eleventyConfig.addPassthroughCopy("style.css");
  eleventyConfig.addPassthroughCopy("kml-viewer.html");
  
  // Set custom input and output directories
  return {
    dir: {
      input: ".",
      output: "../../build/web",
      includes: "_includes"
    }
  };
};
