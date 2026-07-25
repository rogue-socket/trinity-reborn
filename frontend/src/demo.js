import topic from "../../fixtures/topic.json";
import deltaOne from "../../fixtures/delta-01-initial.json";
import deltaTwo from "../../fixtures/delta-02-update.json";
import deltaThree from "../../fixtures/delta-03-conflict.json";

export const demoScenario = {
  topic,
  deltas: [deltaOne, deltaTwo, deltaThree],
};
