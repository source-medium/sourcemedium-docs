const yaml = require("yaml");
const fs = require("fs");

let yamlFile = fs.readFileSync("yaml-files/dda_customers.yml", "utf8");
let loadedYaml = yaml.parse(yamlFile);

for (let i = 0; i < loadedYaml.models.length; i++) {
    console.log(loadedYaml.models[i].name);
    for (let k = 0; k < loadedYaml.models[i].columns.length; k++) {
        console.log(loadedYaml.models[i].columns[k].name, loadedYaml.models[i].columns[k].data_type);
      }
  }