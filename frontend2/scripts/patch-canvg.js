const fs = require("fs");
const esPath = "./node_modules/canvg/lib/index.es.js";
const cjsPath = "./node_modules/canvg/lib/index.cjs";

if (fs.existsSync(esPath)) {
  let content = fs.readFileSync(esPath, "utf-8");
  content = content.replace(/import requestAnimationFrame from 'raf';/g, "const requestAnimationFrame = typeof window !== 'undefined' && window.requestAnimationFrame ? window.requestAnimationFrame : function(cb){setTimeout(cb,16)};");
  fs.writeFileSync(esPath, content);
}

if (fs.existsSync(cjsPath)) {
  let content = fs.readFileSync(cjsPath, "utf-8");
  content = content.replace(/var requestAnimationFrame = require\('raf'\);/g, "var requestAnimationFrame = typeof window !== 'undefined' && window.requestAnimationFrame ? window.requestAnimationFrame : function(cb){setTimeout(cb,16)};");
  fs.writeFileSync(cjsPath, content);
}

console.log("Patched canvg to remove raf dependency for Turbopack!");
