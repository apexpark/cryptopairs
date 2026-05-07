import { cueDisplayedVariant } from "../App";
import type { Cue, CueSelectionState } from "../types";

function buildCue(
  validationState: CueSelectionState["validation_state"],
  storedChampionVariant: string | null = "COINTEGRATION_Z"
): Cue {
  return {
    selected_variant: "ROBUST_Z",
    selection_state: {
      best_variant: "ROBUST_Z",
      best_opportunity_score: 2.4,
      best_direction_hint: "LONG_SPREAD",
      best_confidence_band: "HIGH",
      stored_champion_variant: storedChampionVariant,
      stored_champion_score: storedChampionVariant ? 1.8 : null,
      stored_champion_direction_hint: storedChampionVariant ? "SHORT_SPREAD" : null,
      stored_champion_confidence_band: storedChampionVariant ? "MEDIUM" : null,
      transition_decision: storedChampionVariant ? "KEEP_CHAMPION" : "INITIALIZE",
      score_delta_to_champion: storedChampionVariant ? 0.6 : null,
      drift_active: storedChampionVariant != null && storedChampionVariant !== "ROBUST_Z",
      source: storedChampionVariant ? "STORED_CHAMPION_PROJECTION" : "EVALUATED_BEST",
      validation_state: validationState,
    },
  } as Cue;
}

describe("cueDisplayedVariant", () => {
  it("renders projection failures as blocked instead of showing the stored champion", () => {
    expect(cueDisplayedVariant(buildCue("CHAMPION_PROJECTION_FAILED"))).toBe("BLOCKED");
  });

  it.each(["CHAMPION_PROJECTED", "CHAMPION_PROJECTED_BLOCKED"] as const)(
    "preserves stored champion display for %s",
    (validationState) => {
      expect(cueDisplayedVariant(buildCue(validationState))).toBe("COINTEGRATION_Z");
    }
  );

  it("falls back to the selected variant when no stored champion exists", () => {
    expect(cueDisplayedVariant(buildCue("NO_STORED_CHAMPION", null))).toBe("ROBUST_Z");
  });

  it("preserves legacy cues without selection diagnostics", () => {
    expect(cueDisplayedVariant({ selected_variant: "VOL_NORMALIZED" } as Cue)).toBe(
      "VOL_NORMALIZED"
    );
  });
});
